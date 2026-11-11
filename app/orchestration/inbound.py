"""Inbound orchestration graph: dedup, slot-filling, acknowledgement, planning and the review queue."""

from pathlib import Path
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from app.extraction.base import Extraction
from app.orchestration import router
from app.orchestration.acks import ack_text, language_key
from app.orchestration.review import build_review_context
from app.orchestration.slots import SLOT_SPECS, missing_slots, next_question
from app.orchestration.taxonomy import UNCLASSIFIED
from app.orchestration.workflow import PlanState, plan_graph
from app.schemas.contracts import (
    EvidenceFact,
    InboundAck,
    InboundResult,
    IntentMatch,
    MessageSubmission,
)
from app.state import StateLoadError, StateVersionMismatch
from app.store.ledger import InboundLedger, ledger as default_ledger


class InboundState(PlanState, total=False):
    original: MessageSubmission
    ledger: InboundLedger
    conversation_id: str
    rounds: int
    duplicate: bool
    routed_action: str
    queue: bool
    payload: dict


def _extraction_from_result(result: dict) -> Extraction:
    event = result["event"]
    return Extraction(
        intents=[IntentMatch.model_validate(item) for item in event.get("intents", [])],
        facts=[EvidenceFact.model_validate(item) for item in event.get("extracted_facts", [])],
        inferences=dict(event.get("inferences", {})),
        uncertainties=list(event.get("uncertainties", [])),
        mode=result.get("mode", "rules_mock"),
    )


def _receipt(message: MessageSubmission, status: str) -> InboundAck:
    language = language_key(message.language)
    return InboundAck(kind="receipt", status=status, text=ack_text("receipt", message.language), language=language)


def _complete(message: MessageSubmission) -> InboundAck:
    language = language_key(message.language)
    return InboundAck(kind="complete", status="accepted", text=ack_text("complete", message.language), language=language)


def _queue_record(result: dict, routed_action: str) -> dict:
    event = result.get("event") or {}
    recommendation = result.get("recommendation") or {}
    return {
        "event_id": event.get("event_id") or "unknown",
        "event_type": event.get("event_type", UNCLASSIFIED),
        "routed_action": routed_action,
        "summary": recommendation.get("summary")
        or f"Awaiting human review: {event.get('event_type', UNCLASSIFIED)}",
        "recommendation_status": recommendation.get("review_status"),
        "mode": result.get("mode", "rules_mock"),
        "state_version": event.get("state_version"),
        "why": build_review_context(result),
    }


def _dedup(flow: InboundState) -> dict:
    message = flow["original"]
    previous = flow["ledger"].get_result(message.message_id)
    if previous is None:
        return {"duplicate": False}
    replayed = dict(previous)
    replayed["ack"] = {**replayed["ack"], "status": "duplicate"}
    replayed["duplicate"] = True
    return {"duplicate": True, "payload": replayed}


def _after_dedup(flow: InboundState) -> str:
    return "finish" if flow.get("duplicate") else "intake"


def _intake(flow: InboundState) -> dict:
    message = flow["original"]
    conversation_id = message.conversation_id or message.message_id
    intake = flow["ledger"].get_intake(conversation_id)
    rounds = (intake.rounds + 1) if intake else 0
    submission = message
    if intake:
        submission = message.model_copy(update={"text": "\n".join(intake.texts + [message.text])})
    return {"submission": submission, "conversation_id": conversation_id, "rounds": rounds}


def _slot_gate(flow: InboundState) -> dict:
    message = flow["original"]
    result = flow["result"]
    rounds = flow.get("rounds", 0)

    event = result["event"]
    intake = flow["ledger"].get_intake(flow["conversation_id"])
    if intake:
        event["source_message_ids"] = intake.message_ids + [message.message_id]
        result["event"] = event

    intent = event["event_type"]
    extraction = _extraction_from_result(result)
    party_type = message.sender.party_type if message.sender else "unknown"
    missing = missing_slots(intent, extraction)
    spec = SLOT_SPECS.get(intent)

    question = None
    if missing and spec is not None and rounds < spec.max_rounds:
        question = next_question(intent, extraction, party_type, message.language)

    handler = router.resolve(intent)
    recommendation = result.get("recommendation") or {}

    if question:
        routed_action = "slot_question"
    elif handler is not None and not missing and recommendation.get("review_status") == "pending_review":
        routed_action = result.get("routed_action", "human_triage")
    else:
        routed_action = "human_triage"

    completion = _complete(message) if not missing and intent != UNCLASSIFIED else None
    ack_status = "triaged" if routed_action == "human_triage" else "accepted"
    payload = InboundResult(
        ack=_receipt(message, ack_status),
        completion_ack=completion,
        event=event,
        routed_action=routed_action,
        question=question,
        recommendation=result.get("recommendation"),
        mode=result.get("mode", "rules_mock"),
        rounds=rounds,
    ).model_dump(mode="json")

    return {
        "payload": payload,
        "routed_action": routed_action,
        "queue": routed_action == "human_triage"
        or recommendation.get("review_status") == "pending_review",
    }


def _after_slot_gate(flow: InboundState) -> str:
    return "ask" if flow["routed_action"] == "slot_question" else "close"


def _ask_follow_up(flow: InboundState) -> dict:
    message = flow["original"]
    flow["ledger"].open_intake(
        flow["conversation_id"], message.message_id, message.text, flow.get("rounds", 0) + 1
    )
    flow["ledger"].record_result(message.message_id, flow["payload"])
    return {}


def _close_and_queue(flow: InboundState) -> dict:
    message = flow["original"]
    flow["ledger"].close_intake(flow["conversation_id"])
    if flow.get("queue"):
        flow["ledger"].queue_for_review(
            flow["result"]["event"]["event_id"],
            _queue_record(flow["result"], flow["routed_action"]),
        )
    flow["ledger"].record_result(message.message_id, flow["payload"])
    return {}


def _build_inbound_graph():
    builder = StateGraph(InboundState)
    builder.add_node("dedup", _dedup)
    builder.add_node("intake", _intake)
    builder.add_node("plan", plan_graph)
    builder.add_node("slot_gate", _slot_gate)
    builder.add_node("ask_follow_up", _ask_follow_up)
    builder.add_node("close_and_queue", _close_and_queue)

    builder.add_edge(START, "dedup")
    builder.add_conditional_edges("dedup", _after_dedup, {"intake": "intake", "finish": END})
    builder.add_edge("intake", "plan")
    builder.add_edge("plan", "slot_gate")
    builder.add_conditional_edges(
        "slot_gate", _after_slot_gate, {"ask": "ask_follow_up", "close": "close_and_queue"}
    )
    builder.add_edge("ask_follow_up", END)
    builder.add_edge("close_and_queue", END)
    return builder.compile()


inbound_graph = _build_inbound_graph()


def _record_processing_error(message: MessageSubmission, exc: Exception, ledger: InboundLedger) -> dict:
    reason = type(exc).__name__
    conversation_id = message.conversation_id or message.message_id
    intake = ledger.get_intake(conversation_id)
    rounds = (intake.rounds + 1) if intake else 0
    payload = InboundResult(
        ack=_receipt(message, "triaged"),
        routed_action="human_triage",
        processing_error=reason,
        rounds=rounds,
    ).model_dump(mode="json")
    ledger.record_result(message.message_id, payload)
    ledger.queue_for_review(
        f"error-{message.message_id}",
        {
            "event_id": f"error-{message.message_id}",
            "event_type": "processing_error",
            "routed_action": "human_triage",
            "summary": f"Message could not be processed: {reason}",
            "recommendation_status": None,
            "mode": "rules_mock",
            "state_version": message.state_version,
        },
    )
    return payload


def process_inbound(
    message: MessageSubmission,
    ledger: InboundLedger = default_ledger,
    data_dir: Path | None = None,
) -> dict:
    """Run one inbound message through the graph. Failures are acknowledged and triaged, never dropped."""
    try:
        output = inbound_graph.invoke(
            {"original": message, "ledger": ledger, "data_dir": data_dir, "duplicate": False}
        )
    except (StateVersionMismatch, StateLoadError) as exc:
        return _record_processing_error(message, exc, ledger)
    return output["payload"]
