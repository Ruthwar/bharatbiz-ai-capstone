"""Inbound orchestration: dedup, slot-filling rounds, acknowledgement and routing."""

from pathlib import Path

from app.extraction.base import Extraction
from app.orchestration import router
from app.orchestration.acks import ack_text, language_key
from app.orchestration.slots import SLOT_SPECS, missing_slots, next_question
from app.orchestration.taxonomy import UNCLASSIFIED
from app.orchestration.workflow import process_message
from app.schemas.contracts import (
    EvidenceFact,
    InboundAck,
    InboundResult,
    IntentMatch,
    MessageSubmission,
)
from app.state import StateLoadError, StateVersionMismatch
from app.store.ledger import InboundLedger, ledger as default_ledger


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
    }


def process_inbound(
    message: MessageSubmission,
    ledger: InboundLedger = default_ledger,
    data_dir: Path | None = None,
) -> dict:
    previous = ledger.get_result(message.message_id)
    if previous is not None:
        replayed = dict(previous)
        replayed["ack"] = {**replayed["ack"], "status": "duplicate"}
        replayed["duplicate"] = True
        return replayed

    conversation_id = message.conversation_id or message.message_id
    intake = ledger.get_intake(conversation_id)
    rounds = (intake.rounds + 1) if intake else 0
    submission = message
    if intake:
        submission = message.model_copy(update={"text": "\n".join(intake.texts + [message.text])})

    try:
        result = process_message(submission, data_dir=data_dir)
    except (StateVersionMismatch, StateLoadError) as exc:
        reason = type(exc).__name__
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

    event = result["event"]
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

    completion = None
    if not missing and intent != UNCLASSIFIED:
        completion = _complete(message)

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

    if routed_action == "slot_question":
        ledger.open_intake(conversation_id, message.message_id, message.text, rounds + 1)
    else:
        ledger.close_intake(conversation_id)

    if routed_action == "human_triage" or recommendation.get("review_status") == "pending_review":
        ledger.queue_for_review(event["event_id"], _queue_record(result, routed_action))

    ledger.record_result(message.message_id, payload)
    return payload
