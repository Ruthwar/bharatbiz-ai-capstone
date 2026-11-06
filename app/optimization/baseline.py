from datetime import date
from decimal import Decimal

from app.agents.cashflow import project_cash
from app.agents.orders import affected_orders
from app.schemas.contracts import (
    AllocationRow,
    BusinessState,
    CandidatePlan,
    SupplierOption,
)


def allocate_fifo(orders: list[dict], available_by_sku: dict[str, int]) -> list[dict]:
    remaining = dict(available_by_sku)
    results = []
    for order in sorted(orders, key=lambda row: (row["order_date"], row["order_id"])):
        sku = order["sku_id"]
        fulfilled = min(order["quantity_units"], remaining.get(sku, 0))
        remaining[sku] = remaining.get(sku, 0) - fulfilled
        results.append({
            "order_id": order["order_id"],
            "sku_id": sku,
            "fulfilled_units": fulfilled,
            "unmet_units": order["quantity_units"] - fulfilled,
        })
    return results


def _build_plan(
    state: BusinessState,
    sku_id: str,
    immediate_available_units: int,
    supplier_option: SupplierOption | None,
    planning_horizon: date,
) -> CandidatePlan:
    remaining_stock = max(0, immediate_available_units)
    remaining_supplier = supplier_option.quantity_units if supplier_option else 0
    allocations = []

    for order in affected_orders(state, sku_id):
        requested = order["quantity_units"]
        stock_fulfilled = min(requested, remaining_stock)
        remaining_stock -= stock_fulfilled
        supplier_fulfilled = min(requested - stock_fulfilled, remaining_supplier)
        remaining_supplier -= supplier_fulfilled
        fulfilled = stock_fulfilled + supplier_fulfilled
        due = date.fromisoformat(order["requested_delivery_date"])
        late = (
            supplier_fulfilled
            if supplier_option and supplier_option.scenario_arrival_date > due
            else 0
        )
        allocations.append(
            AllocationRow(
                order_id=order["order_id"],
                sku_id=sku_id,
                requested_delivery_date=due,
                requested_units=requested,
                stock_fulfilled_units=stock_fulfilled,
                supplier_fulfilled_units=supplier_fulfilled,
                fulfilled_units=fulfilled,
                late_units=late,
                unmet_units=requested - fulfilled,
            )
        )

    total_cost = supplier_option.total_cost_rupees if supplier_option else Decimal("0.00")
    return CandidatePlan(
        candidate_id=f"supplier-{supplier_option.supplier_id}" if supplier_option else "stock-only",
        state_version=state.state_version,
        planning_horizon=planning_horizon,
        supplier_option=supplier_option,
        allocations=allocations,
        total_requested_units=sum(row.requested_units for row in allocations),
        fulfilled_units=sum(row.fulfilled_units for row in allocations),
        late_units=sum(row.late_units for row in allocations),
        unmet_units=sum(row.unmet_units for row in allocations),
        total_cost_rupees=total_cost,
        cash_projection=project_cash(state, total_cost),
    )


def build_candidate_plans(
    state: BusinessState,
    sku_id: str,
    immediate_available_units: int,
    supplier_options: list[SupplierOption],
    planning_horizon: date,
) -> list[CandidatePlan]:
    plans = [_build_plan(state, sku_id, immediate_available_units, None, planning_horizon)]
    for option in supplier_options:
        if not option.feasible:
            continue
        plan = _build_plan(state, sku_id, immediate_available_units, option, planning_horizon)
        if plan.cash_projection.feasible:
            plans.append(plan)
    return plans


def select_best_plan(plans: list[CandidatePlan]) -> CandidatePlan:
    if not plans:
        raise ValueError("No candidate plans are available")

    def rank(plan: CandidatePlan) -> tuple:
        option = plan.supplier_option
        return (
            plan.unmet_units,
            plan.late_units,
            option.scenario_arrival_date if option else date.max,
            plan.total_cost_rupees,
            plan.candidate_id,
        )

    return min(plans, key=rank)
