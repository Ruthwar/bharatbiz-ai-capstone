from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.contracts import MessageSubmission


class ReceiptOverlay(BaseModel):
    receipt_id: str
    retailer_id: str
    amount_rupees: Decimal = Field(gt=0)
    expected_date: date
    actual_date: date


class ScenarioOverlays(BaseModel):
    demand_multiplier: Decimal = Field(default=Decimal("1"), gt=0)
    demand_order_ids: list[str] = Field(default_factory=list)
    demand_rounding: Literal["ceiling"] = "ceiling"
    original_supplier_id: str | None = None
    supplier_delay_days: int = Field(default=0, ge=0)
    delayed_incoming_units: int | None = Field(default=None, ge=0)
    physical_count_delta: int | None = None
    opening_cash_rupees: Decimal | None = Field(default=None, ge=0)
    receipts: list[ReceiptOverlay] = Field(default_factory=list)
    planning_horizon: date | None = None
    procurement_costs: Literal["immediate_outflow"] = "immediate_outflow"


class ScenarioFixture(BaseModel):
    scenario_id: str = Field(pattern=r"^SCN-\d{3}$")
    name: str
    description: str = ""
    message: MessageSubmission | None = None
    target_sku_id: str | None = None
    overlays: ScenarioOverlays = Field(default_factory=ScenarioOverlays)
    history: list[dict] = Field(default_factory=list)
    observations: list[dict] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
    expected: dict = Field(default_factory=dict)
    assumptions: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_target(self):
        if self.target_sku_id is None and self.scenario_id not in {"SCN-006", "SCN-007", "SCN-009"}:
            raise ValueError(f"{self.scenario_id}: target_sku_id is required")
        return self
