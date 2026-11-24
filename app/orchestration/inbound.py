"""Inbound orchestration graph: dedup, slot-filling, acknowledgement, planning and the review queue."""

from pathlib import Path
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from app.extraction.base import Extraction
from app.extraction.rules import product_clarification_options
from app.orchestration import router
from app.orchestration.acks import ack_text, language_key
from app.orchestration.retail import persist_retail
from app.orchestration.review import build_review_context
from app.observability import trace_scope
from app.orchestration.slots import SLOT_SPECS, missing_slots, next_question
from app.orchestration.taxonomy import UNCLASSIFIED
from app.orchestration.workflow import PlanState, plan_graph
from app.scenarios.contracts import ScenarioFixture
from app.schemas.contracts import (
    EvidenceFact,
    InboundAck,
    InboundResult,
    IntentMatch,
    MessageSubmission,
)
from app.state import StateLoadError, StateVersionMismatch
from app.store.ledger import InboundLedger, ledger as default_ledger
from app.store.retail import RetailStore, retail_store as default_retail_store


class InboundState(PlanState, total=False):
    original: MessageSubmission
    ledger: InboundLedger
    retail_store: RetailStore
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
        "decision_mode": result.get("decision_mode", "deterministic"),
        "state_version": event.get("state_version"),
        "case_id": (result.get("retail_context") or {}).get("case_id"),
        "draft_id": (result.get("retail_context") or {}).get("draft_id"),
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
    # rounds counts questions already asked, so the cap compares questions asked with max_rounds.
    rounds = intake.rounds if intake else 0
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
    available = set()
    if message.sender and message.sender.party_id:
        if party_type == "retailer":
            available.add("retailer_id")
        elif party_type == "supplier":
            available.add("supplier_id")
    missing = missing_slots(intent, extraction, available)
    dynamic_slot = (result.get("case_context") or {}).get("clarification_slot")
    additional_missing = []
    if dynamic_slot == "order_reference" and dynamic_slot not in missing:
        additional_missing.append(dynamic_slot)
        missing.append(dynamic_slot)
    spec = SLOT_SPECS.get(intent)

    question = None
    if missing and spec is not None and rounds < spec.max_rounds:
        product_options = None
        if "product" in missing:
            supplier_fact = extraction.fact("supplier_id")
            supplier_id = supplier_fact.value if supplier_fact else (
                message.sender.party_id if message.sender and party_type == "supplier" else None
            )
            product_options = product_clarification_options(
                flow["business_state"], flow["submission"].text, supplier_id
            )
        question = next_question(
            intent,
            extraction,
            party_type,
            message.language,
            available=available,
            additional_missing=additional_missing,
            product_options=product_options,
        )
        if additional_missing:
            question = result.get("question") or question

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
        decision_mode=result.get("decision_mode", "deterministic"),
        rounds=rounds,
    ).model_dump(mode="json")
    payload["result"] = result

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
    result = flow["result"]
    persist_retail(flow["submission"], result, flow["business_state"], flow["retail_store"])
    flow["payload"]["result"] = result
    if flow.get("queue"):
        flow["ledger"].queue_for_review(
            result["event"]["event_id"],
            _queue_record(result, flow["routed_action"]),
        )
    flow["ledger"].close_intake(flow["conversation_id"])
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
    rounds = intake.rounds if intake else 0
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
    scenario: ScenarioFixture | None = None,
    retail_store: RetailStore = default_retail_store,
    decision_mode: str = "deterministic",
) -> dict:
    """Run one inbound message through the graph. Failures are acknowledged and triaged, never dropped."""
    conversation_id = message.conversation_id or message.message_id
    with trace_scope(
        f"inbound:{conversation_id}",
        scenario_id=scenario.scenario_id if scenario else None,
        source="inbound",
    ):
        try:
            output = inbound_graph.invoke(
                {
                    "original": message,
                    "ledger": ledger,
                    "retail_store": retail_store,
                    "data_dir": data_dir,
                    "scenario": scenario,
                    "decision_mode": decision_mode,
                    "duplicate": False,
                }
            )
        except (StateVersionMismatch, StateLoadError) as exc:
            return _record_processing_error(message, exc, ledger)
    return output["payload"]
