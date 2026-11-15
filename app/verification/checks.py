from datetime import timedelta
from decimal import Decimal

from app.agents.cashflow import project_dated_cash
from app.optimization.context import PlanningView, build_planning_view
from app.scenarios.contracts import ScenarioOverlays
from app.schemas.contracts import BusinessState, CandidatePlan, VerificationResult


def verify_cash(ending_cash_rupees: Decimal, minimum_buffer_rupees: Decimal) -> list[str]:
    return [] if ending_cash_rupees >= minimum_buffer_rupees else ["minimum_cash_buffer_breached"]


def verify_allocations(rows: list[dict], stock_by_sku: dict[str, int]) -> list[str]:
    totals: dict[str, int] = {}
    for row in rows:
        totals[row["sku_id"]] = totals.get(row["sku_id"], 0) + row["fulfilled_units"]
    return [f"stock_exceeded:{sku}" for sku, total in totals.items() if total > stock_by_sku.get(sku, 0)]


def verify_plan(
    state: BusinessState,
    plan: CandidatePlan,
    immediate_available_units: int,
    planning_view: PlanningView | None = None,
    receipt_timing: str = "actual",
) -> VerificationResult:
    violations = []
    if plan.state_version != state.state_version:
        violations.append("state_version_mismatch")

    source_orders = planning_view.orders if planning_view else state.open_orders
    orders = {row["order_id"]: row for row in source_orders}
    seen_orders = set()
    for row in plan.allocations:
        order = orders.get(row.order_id)
        if order is None:
            violations.append(f"unknown_order:{row.order_id}")
            continue
        if row.order_id in seen_orders:
            violations.append(f"duplicate_order_allocation:{row.order_id}")
        seen_orders.add(row.order_id)
        if order["sku_id"] != row.sku_id:
            violations.append(f"order_sku_mismatch:{row.order_id}")
        if order["quantity_units"] != row.requested_units:
            violations.append(f"requested_quantity_mismatch:{row.order_id}")
        if order["requested_delivery_date"] != row.requested_delivery_date.isoformat():
            violations.append(f"requested_date_mismatch:{row.order_id}")
        if row.fulfilled_units != row.stock_fulfilled_units + row.supplier_fulfilled_units:
            violations.append(f"fulfilment_split_mismatch:{row.order_id}")
        if row.fulfilled_units + row.unmet_units != row.requested_units:
            violations.append(f"allocation_conservation_failed:{row.order_id}")
        expected_late = 0
        if plan.supplier_option and plan.supplier_option.scenario_arrival_date > row.requested_delivery_date:
            expected_late = row.supplier_fulfilled_units
        if row.late_units != expected_late:
            violations.append(f"late_quantity_mismatch:{row.order_id}")
        if not plan.supplier_option and row.supplier_fulfilled_units:
            violations.append(f"unexpected_supplier_allocation:{row.order_id}")

    if planning_view:
        expected_order_ids = {row["order_id"] for row in planning_view.orders}
        for missing in sorted(expected_order_ids - seen_orders):
            violations.append(f"missing_order_allocation:{missing}")

    stock_allocated = sum(row.stock_fulfilled_units for row in plan.allocations)
    if stock_allocated > immediate_available_units:
        violations.append(f"stock_exceeded:{plan.allocations[0].sku_id if plan.allocations else 'unknown'}")

    opening_cash = planning_view.opening_cash_rupees if planning_view else state.cash_balance_rupees
    option = plan.supplier_option
    expected_cost = Decimal("0.00")
    if option:
        supplier_allocated = sum(row.supplier_fulfilled_units for row in plan.allocations)
        if supplier_allocated > option.quantity_units:
            violations.append(f"supplier_allocation_exceeded:{option.supplier_id}")
        if option.scenario_arrival_date > plan.planning_horizon:
            violations.append(f"arrival_after_planning_horizon:{option.supplier_id}")
        offer = next(
            (
                row for row in state.supplier_offers
                if row["supplier_id"] == option.supplier_id and row["sku_id"] == option.sku_id
            ),
            None,
        )
        if offer is None:
            violations.append(f"invalid_supplier_offer:{option.supplier_id}:{option.sku_id}")
        else:
            if option.quantity_units < offer["min_order_units"]:
                violations.append(f"minimum_order_breached:{option.supplier_id}")
            if option.quantity_units > offer["capacity_units"]:
                violations.append(f"supplier_capacity_exceeded:{option.supplier_id}")
            if option.unit_cost_rupees != offer["unit_cost_rupees"]:
                violations.append(f"supplier_unit_cost_mismatch:{option.supplier_id}")
            expected_cost = option.quantity_units * offer["unit_cost_rupees"]
            if planning_view:
                expected_lead = offer["lead_time_days"] + (
                    planning_view.supplier_delay_days
                    if option.supplier_id == planning_view.original_supplier_id
                    else 0
                )
                expected_arrival = state.as_of.date() + timedelta(days=expected_lead)
                if option.lead_time_days != expected_lead or option.scenario_arrival_date != expected_arrival:
                    violations.append(f"supplier_arrival_mismatch:{option.supplier_id}")
    elif plan.total_cost_rupees:
        violations.append("unexpected_stock_only_cost")

    if planning_view:
        expected_projection = project_dated_cash(
            opening_cash,
            state.minimum_cash_buffer_rupees,
            expected_cost,
            planning_view.receipts,
            state.as_of.date(),
            plan.planning_horizon,
            receipt_timing,
        )
    else:
        expected_ending = opening_cash - expected_cost
        expected_projection = plan.cash_projection.model_copy(
            update={
                "ending_cash_rupees": expected_ending,
                "headroom_rupees": expected_ending - state.minimum_cash_buffer_rupees,
            }
        )

    if plan.total_cost_rupees != expected_cost:
        violations.append("candidate_cost_mismatch")
    if plan.cash_projection.ending_cash_rupees != expected_projection.ending_cash_rupees:
        violations.append("cash_projection_mismatch")
    if plan.cash_projection.headroom_rupees != expected_projection.headroom_rupees:
        violations.append("cash_headroom_mismatch")
    if planning_view:
        if plan.cash_projection.daily_schedule != expected_projection.daily_schedule:
            violations.append("cash_schedule_mismatch")
        if not expected_projection.feasible:
            violations.append("minimum_cash_buffer_breached")
    else:
        violations.extend(verify_cash(expected_projection.ending_cash_rupees, state.minimum_cash_buffer_rupees))

    totals = {
        "total_requested_units": sum(row.requested_units for row in plan.allocations),
        "fulfilled_units": sum(row.fulfilled_units for row in plan.allocations),
        "late_units": sum(row.late_units for row in plan.allocations),
        "unmet_units": sum(row.unmet_units for row in plan.allocations),
    }
    for field, expected in totals.items():
        if getattr(plan, field) != expected:
            violations.append(f"plan_total_mismatch:{field}")

    unique_violations = list(dict.fromkeys(violations))
    return VerificationResult(valid=not unique_violations, violations=unique_violations)


def verify_scenario_plan(
    state: BusinessState,
    plan: CandidatePlan,
    overlays: ScenarioOverlays,
    sku_id: str,
    receipt_timing: str = "actual",
) -> VerificationResult:
    view = build_planning_view(state, sku_id, overlays)
    return verify_plan(
        state,
        plan,
        view.immediate_available_units,
        planning_view=view,
        receipt_timing=receipt_timing,
    )
