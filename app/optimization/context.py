from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_CEILING

from app.scenarios.contracts import ReceiptOverlay, ScenarioOverlays
from app.schemas.contracts import BusinessState


@dataclass(frozen=True)
class PlanningView:
    state: BusinessState
    sku_id: str
    orders: tuple[dict, ...]
    immediate_available_units: int
    planning_horizon: date
    opening_cash_rupees: Decimal
    receipts: tuple[ReceiptOverlay, ...]
    original_supplier_id: str | None
    supplier_delay_days: int
    overlay_audit: tuple[dict, ...]
    book_on_hand_units: int
    counted_on_hand_units: int


def build_planning_view(
    state: BusinessState,
    sku_id: str,
    overlays: ScenarioOverlays | None = None,
) -> PlanningView:
    overlays = overlays or ScenarioOverlays()
    inventory = next((row for row in state.inventory if row["sku_id"] == sku_id), None)
    if inventory is None:
        raise ValueError(f"Unknown inventory SKU: {sku_id}")

    selected_ids = set(overlays.demand_order_ids)
    audit: list[dict] = []
    orders = []
    for source in state.open_orders:
        if source["sku_id"] != sku_id or source["status"] != "open":
            continue
        row = dict(source)
        if overlays.demand_multiplier != 1 and (not selected_ids or row["order_id"] in selected_ids):
            before = row["quantity_units"]
            adjusted = int(
                (Decimal(before) * overlays.demand_multiplier).to_integral_value(rounding=ROUND_CEILING)
            )
            row["quantity_units"] = adjusted
            audit.append(
                {
                    "kind": "demand",
                    "order_id": row["order_id"],
                    "before_units": before,
                    "after_units": adjusted,
                    "multiplier": str(overlays.demand_multiplier),
                    "rounding": overlays.demand_rounding,
                }
            )
        orders.append(row)
    orders.sort(key=lambda row: (row["order_date"], row["order_id"]))

    book_on_hand = inventory["on_hand_units"]
    counted_on_hand = book_on_hand + (overlays.physical_count_delta or 0)
    if counted_on_hand < 0:
        raise ValueError("Reported physical count cannot be negative")
    if counted_on_hand < inventory["reserved_units"]:
        raise ValueError("Reported physical count is below reserved stock; reconciliation is required")
    if overlays.physical_count_delta is not None:
        audit.append(
            {
                "kind": "physical_count",
                "sku_id": sku_id,
                "book_on_hand_units": book_on_hand,
                "count_delta": overlays.physical_count_delta,
                "counted_on_hand_units": counted_on_hand,
                "reserved_units": inventory["reserved_units"],
            }
        )

    delayed_units = overlays.delayed_incoming_units or 0
    if delayed_units > inventory["incoming_units"]:
        raise ValueError("Delayed incoming units exceed available incoming units")
    immediate = max(
        0,
        counted_on_hand - inventory["reserved_units"] + inventory["incoming_units"] - delayed_units,
    )
    if delayed_units:
        audit.append(
            {
                "kind": "supplier_delay",
                "supplier_id": overlays.original_supplier_id,
                "delay_days": overlays.supplier_delay_days,
                "delayed_incoming_units": delayed_units,
                "scenario_usable_units": immediate,
            }
        )

    horizon = overlays.planning_horizon or max(
        (date.fromisoformat(row["requested_delivery_date"]) for row in orders),
        default=state.as_of.date(),
    )
    opening_cash = (
        overlays.opening_cash_rupees
        if overlays.opening_cash_rupees is not None
        else state.cash_balance_rupees
    )
    if opening_cash != state.cash_balance_rupees:
        audit.append(
            {
                "kind": "opening_cash",
                "base_cash_rupees": str(state.cash_balance_rupees),
                "scenario_cash_rupees": str(opening_cash),
            }
        )
    for receipt in overlays.receipts:
        audit.append({"kind": "receipt", **receipt.model_dump(mode="json")})

    return PlanningView(
        state=state,
        sku_id=sku_id,
        orders=tuple(orders),
        immediate_available_units=immediate,
        planning_horizon=horizon,
        opening_cash_rupees=opening_cash,
        receipts=tuple(overlays.receipts),
        original_supplier_id=overlays.original_supplier_id,
        supplier_delay_days=overlays.supplier_delay_days,
        overlay_audit=tuple(audit),
        book_on_hand_units=book_on_hand,
        counted_on_hand_units=counted_on_hand,
    )
