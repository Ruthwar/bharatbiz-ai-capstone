import re
from uuid import uuid4

from app.schemas.contracts import BusinessEvent, EvidenceFact, MessageSubmission

RULES = (
    ("supplier_delay", re.compile(r"delay|late|postpon", re.I)),
    ("delivery_complaint", re.compile(r"delivery|delivered|arriv", re.I)),
    ("product_request", re.compile(r"request|need|asking|pack", re.I)),
    ("scheme_question", re.compile(r"scheme|offer|discount", re.I)),
    ("competitor_observation", re.compile(r"competitor|nearby shop", re.I)),
)


def process_message(message: MessageSubmission) -> dict:
    """Rules-first baseline: classify obvious language and preserve source evidence."""
    event_type = next((name for name, pattern in RULES if pattern.search(message.text)), "other")
    span = next((m.group(0) for _, pattern in RULES if (m := pattern.search(message.text))), "")
    facts = [EvidenceFact(field="trigger_phrase", value=span, evidence_span=span)] if span else []
    event = BusinessEvent(
        event_id=f"evt-{uuid4().hex[:10]}",
        source_message_ids=[message.message_id],
        event_type=event_type,
        extracted_facts=facts,
        uncertainties=["Product, quantity, date or business reference not asserted unless explicitly extracted."],
        human_review_required=True,
        state_version=message.state_version,
    )
    return {"message": message.model_dump(mode="json"), "event": event.model_dump(), "mode": "rules_mock"}
