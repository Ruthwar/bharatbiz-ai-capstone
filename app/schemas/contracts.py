from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class MessageSubmission(BaseModel):
    message_id: str = Field(min_length=1)
    source_type: Literal["retailer_message", "sales_visit", "supplier_update", "synthetic"]
    text: str = Field(min_length=1)
    observed_at: datetime
    language: str = "unknown"
    consent_status: Literal["synthetic", "authorized", "not_applicable"] = "synthetic"
    state_version: str = "sim-v1"


class EvidenceFact(BaseModel):
    field: str
    value: str
    evidence_span: str
    confidence: Literal["reported", "verified"] = "reported"


class BusinessEvent(BaseModel):
    event_id: str
    source_message_ids: list[str]
    event_type: str
    extracted_facts: list[EvidenceFact] = []
    inferences: dict[str, str | bool | None] = {}
    uncertainties: list[str] = []
    human_review_required: bool = True
    status: Literal["pending_review", "needs_clarification", "verified"] = "pending_review"
    state_version: str


class AgentResult(BaseModel):
    agent_name: str
    status: Literal["ok", "needs_clarification", "failed"]
    state_version: str
    proposal: dict = {}
    evidence_refs: list[str] = []
    assumptions: list[str] = []
    warnings: list[str] = []


class BusinessState(BaseModel):
    state_version: str
    as_of: datetime
    inventory: list[dict] = []
    open_orders: list[dict] = []
    suppliers: list[dict] = []
    cash_balance_paise: int
    minimum_cash_buffer_paise: int


class Recommendation(BaseModel):
    recommendation_id: str
    state_version: str
    summary: str
    evidence_refs: list[str] = []
    assumptions: list[str] = []
    warnings: list[str] = []
    review_status: Literal["pending_review", "approved", "rejected", "needs_clarification"] = "pending_review"
    human_approval_required: bool = True
