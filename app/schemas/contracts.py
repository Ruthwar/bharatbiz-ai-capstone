from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


class SenderRef(BaseModel):
    party_type: Literal["retailer", "supplier", "sales_rep", "unknown"] = "unknown"
    party_id: str | None = None
    channel: Literal["chat", "whatsapp", "api"] = "api"


class MessageSubmission(BaseModel):
    message_id: str = Field(min_length=1)
    source_type: Literal["retailer_message", "sales_visit", "supplier_update", "synthetic"]
    text: str = Field(min_length=1)
    observed_at: datetime
    language: str = "unknown"
    consent_status: Literal["synthetic", "authorized", "not_applicable"] = "synthetic"
    state_version: str = Field(min_length=1)
    conversation_id: str | None = None
    sender: SenderRef | None = None


class IntentMatch(BaseModel):
    intent: str
    confidence: float = Field(ge=0, le=1)
    evidence_span: str | None = None


class InboundAck(BaseModel):
    kind: Literal["receipt", "complete"]
    status: Literal["accepted", "duplicate", "triaged", "rejected"] = "accepted"
    text: str
    language: str = "English"


class InboundResult(BaseModel):
    ack: InboundAck
    completion_ack: InboundAck | None = None
    event: dict | None = None
    routed_action: str = "human_triage"
    question: str | None = None
    recommendation: dict | None = None
    mode: str = "rules_mock"
    decision_mode: Literal["deterministic", "policy_grounded_llm"] = "deterministic"
    rounds: int = 0
    duplicate: bool = False
    processing_error: str | None = None


class EvidenceFact(BaseModel):
    field: str
    value: str
    evidence_span: str
    span_start: int | None = None
    span_end: int | None = None
    confidence: Literal["reported", "verified"] = "reported"


class BusinessEvent(BaseModel):
    event_id: str
    source_message_ids: list[str]
    event_type: str
    intents: list[IntentMatch] = Field(default_factory=list)
    taxonomy_version: str = "0.1"
    extracted_facts: list[EvidenceFact] = Field(default_factory=list)
    inferences: dict[str, str | bool | None] = Field(default_factory=dict)
    uncertainties: list[str] = Field(default_factory=list)
    human_review_required: bool = True
    status: Literal["pending_review", "needs_clarification", "verified"] = "pending_review"
    state_version: str


class AgentResult(BaseModel):
    agent_name: str
    status: Literal["ok", "needs_clarification", "failed"]
    state_version: str
    proposal: dict = Field(default_factory=dict)
    evidence_refs: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class BusinessState(BaseModel):
    state_version: str
    as_of: datetime
    products: list[dict] = Field(default_factory=list)
    inventory: list[dict] = Field(default_factory=list)
    open_orders: list[dict] = Field(default_factory=list)
    suppliers: list[dict] = Field(default_factory=list)
    retailers: list[dict] = Field(default_factory=list)
    supplier_offers: list[dict] = Field(default_factory=list)
    cash_balance_rupees: Decimal
    minimum_cash_buffer_rupees: Decimal


class CashDay(BaseModel):
    date: date
    receipts_rupees: Decimal
    procurement_outflow_rupees: Decimal
    closing_cash_rupees: Decimal
    headroom_rupees: Decimal
    feasible: bool


class CashProjection(BaseModel):
    ending_cash_rupees: Decimal
    minimum_buffer_rupees: Decimal
    headroom_rupees: Decimal
    feasible: bool
    daily_schedule: list[CashDay] = Field(default_factory=list)


class CandidateExclusion(BaseModel):
    candidate_id: str
    supplier_id: str | None = None
    reasons: list[str]
    details: dict[str, str] = Field(default_factory=dict)


class SupplierOption(BaseModel):
    supplier_id: str
    supplier_name: str = ""
    sku_id: str
    quantity_units: int = Field(gt=0)
    unit_cost_rupees: Decimal = Field(ge=0)
    total_cost_rupees: Decimal = Field(ge=0)
    lead_time_days: int = Field(ge=0)
    scenario_arrival_date: date
    min_order_units: int = Field(ge=0)
    capacity_units: int = Field(ge=0)
    feasible: bool
    reasons: list[str] = Field(default_factory=list)


class AllocationRow(BaseModel):
    order_id: str
    sku_id: str
    requested_delivery_date: date
    requested_units: int = Field(ge=0)
    stock_fulfilled_units: int = Field(ge=0)
    supplier_fulfilled_units: int = Field(ge=0)
    fulfilled_units: int = Field(ge=0)
    late_units: int = Field(ge=0)
    unmet_units: int = Field(ge=0)


class CandidatePlan(BaseModel):
    candidate_id: str
    state_version: str
    planning_horizon: date
    supplier_option: SupplierOption | None = None
    allocations: list[AllocationRow]
    total_requested_units: int = Field(ge=0)
    fulfilled_units: int = Field(ge=0)
    late_units: int = Field(ge=0)
    unmet_units: int = Field(ge=0)
    total_cost_rupees: Decimal = Field(ge=0)
    cash_projection: CashProjection


class VerificationResult(BaseModel):
    valid: bool
    violations: list[str] = Field(default_factory=list)


class Recommendation(BaseModel):
    recommendation_id: str
    state_version: str
    summary: str
    evidence_refs: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    review_status: Literal["pending_review", "approved", "rejected", "needs_clarification"] = "pending_review"
    human_approval_required: bool = True

## Addition for Inventory Items
class InventoryRow(BaseModel):
    sku_id: str
    on_hand_units: int
    reserved_units: int
    incoming_units: int
    reorder_point_units: int
    unit: str

class OrderRow(BaseModel):
    order_id: str
    retailer_id: str
    sku_id: str
    quantity_units: int
    requested_delivery_date: str
    priority: str
    status: str
    unit: str
    order_date: str

class ProductRow(BaseModel):
    sku_id: str
    product_name: str
    pack_description: str
    base_unit: str
    units_per_case: int
    unit_cost_rupees: Decimal
    category: str
