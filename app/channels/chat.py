"""Demo channel adapter. A WhatsApp webhook would implement the same normalisation."""

import uuid
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.contracts import MessageSubmission, SenderRef

SOURCE_BY_PARTY = {
    "retailer": "retailer_message",
    "supplier": "supplier_update",
    "sales_rep": "sales_visit",
    "unknown": "synthetic",
}


class ChatInbound(BaseModel):
    text: str = Field(min_length=1)
    sender_type: Literal["retailer", "supplier", "sales_rep", "unknown"] = "unknown"
    sender_id: str | None = None
    conversation_id: str | None = None
    language: str = "English"
    message_id: str | None = None
    state_version: str | None = None
    consent_status: Literal["synthetic", "authorized", "not_applicable"] = "synthetic"
    decision_mode: Literal["deterministic", "policy_grounded_llm"] = "deterministic"


def to_submission(payload: ChatInbound, state_version: str) -> MessageSubmission:
    """Channel identity decides source_type and timestamps; the sender never asserts them."""
    message_id = payload.message_id or f"chat-{uuid.uuid4().hex[:12]}"
    return MessageSubmission(
        message_id=message_id,
        source_type=SOURCE_BY_PARTY[payload.sender_type],
        text=payload.text.strip(),
        observed_at=datetime.now(timezone.utc),
        language=payload.language,
        consent_status=payload.consent_status,
        state_version=payload.state_version or state_version,
        conversation_id=payload.conversation_id or message_id,
        sender=SenderRef(party_type=payload.sender_type, party_id=payload.sender_id, channel="chat"),
    )
