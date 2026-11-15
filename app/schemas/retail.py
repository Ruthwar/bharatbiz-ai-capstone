from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

OrderPriority = Literal["high", "normal"]
FulfilmentStatus = Literal["full", "partial", "unfulfilled"]
CaseStatus = Literal["open", "in_progress", "waiting_for_information", "resolved", "closed"]
CasePriority = Literal["high", "normal"]
SignalType = Literal["pack_size_request", "product_request", "competitor_observation"]


class OrderAllocation(BaseModel):
    order_id: str
    retailer_id: str
    retailer_name: str = ""
    sku_id: str
    unit: str
    priority: OrderPriority
    requested_delivery_date: date
    requested_units: int = Field(ge=0)
    allocated_units: int = Field(ge=0)
    unmet_units: int = Field(ge=0)
    status: FulfilmentStatus
    fill_rate: float = Field(ge=0, le=1)
    overdue: bool = False
    service_rank: int = Field(ge=1)


class SkuFulfilment(BaseModel):
    sku_id: str
    unit: str
    available_units: int = Field(ge=0)
    requested_units: int = Field(ge=0)
    allocated_units: int = Field(ge=0)
    unmet_units: int = Field(ge=0)
    fill_rate: float = Field(ge=0, le=1)
    free_after_allocation_units: int = Field(ge=0)


class FulfilmentResult(BaseModel):
    state_version: str
    as_of: date
    rule: str
    include_incoming: bool
    allocations: list[OrderAllocation]
    by_sku: list[SkuFulfilment]
    fill_rate: float = Field(ge=0, le=1)
    changed_vs_fifo: list[dict] = Field(default_factory=list)
    verification_violations: list[str] = Field(default_factory=list)


class CaseProposal(BaseModel):
    case_id: str
    retailer_id: str
    category: str
    priority: CasePriority
    priority_reasons: list[str] = Field(default_factory=list)
    sku_id: str | None = None
    order_ids: list[str] = Field(default_factory=list)
    summary: str
    follow_up: str


class ResponseDraft(BaseModel):
    draft_id: str
    event_id: str
    retailer_id: str
    language: str
    kind: Literal["complaint_ack", "request_ack"]
    text: str
    allowed_tokens: list[str] = Field(default_factory=list)
    safety_violations: list[str] = Field(default_factory=list)
    requires_approval: bool = True
    sent_automatically: bool = False


class MarketObservation(BaseModel):
    observation_id: str
    event_id: str
    signal_type: SignalType
    subject: str
    sku_id: str | None = None
    competitor_name: str = "unknown"
    product_label: str = "unknown"
    offer: str = ""
    area: str = "unknown"
    retailer_id: str | None = None
    reporter_id: str | None = None
    observed_at: str
    observation_text: str
    evidence_span: str
    source_message_id: str


class MarketTheme(BaseModel):
    signal_type: SignalType
    subject: str
    competitor_name: str
    product_label: str
    offer: str
    area: str
    report_count: int
    distinct_reporters: int
    first_seen: str
    last_seen: str
    label: str
    example_evidence: list[str]
    event_ids: list[str]
