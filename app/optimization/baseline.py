from datetime import date
from decimal import Decimal

from app.agents.cashflow import project_cash, project_dated_cash
from app.agents.orders import affected_orders
from app.optimization.context import PlanningView
from app.schemas.contracts import (
    AllocationRow,
    BusinessState,
    CandidateExclusion,
    CandidatePlan,
    CashProjection,
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
    orders: list[dict] | tuple[dict, ...],
    state_version: str,
    sku_id: str,
    immediate_available_units: int,
    supplier_option: SupplierOption | None,
    planning_horizon: date,
    cash_projection: CashProjection,
) -> CandidatePlan:
    remaining_stock = max(0, immediate_available_units)
    remaining_supplier = supplier_option.quantity_units if supplier_option else 0
    allocations = []

    for order in orders:
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
        state_version=state_version,
        planning_horizon=planning_horizon,
        supplier_option=supplier_option,
        allocations=allocations,
        total_requested_units=sum(row.requested_units for row in allocations),
        fulfilled_units=sum(row.fulfilled_units for row in allocations),
        late_units=sum(row.late_units for row in allocations),
        unmet_units=sum(row.unmet_units for row in allocations),
        total_cost_rupees=total_cost,
        cash_projection=cash_projection,
    )


def build_candidate_plans(
    state: BusinessState,
    sku_id: str,
    immediate_available_units: int,
    supplier_options: list[SupplierOption],
    planning_horizon: date,
) -> tuple[list[CandidatePlan], list[CandidateExclusion]]:
    orders = affected_orders(state, sku_id)
    stock_cash = project_cash(state)
    stock_plan = _build_plan(
        orders,
        state.state_version,
        sku_id,
        immediate_available_units,
        None,
        planning_horizon,
        stock_cash,
    )
    plans = []
    exclusions = []
    if stock_cash.feasible:
        plans.append(stock_plan)
    else:
        exclusions.append(
            CandidateExclusion(
                candidate_id="stock-only",
                reasons=["cash_buffer_breached"],
                details={
                    "ending_cash_rupees": str(stock_cash.ending_cash_rupees),
                    "minimum_buffer_rupees": str(stock_cash.minimum_buffer_rupees),
                },
            )
        )
    for option in supplier_options:
        candidate_id = f"supplier-{option.supplier_id}"
        if not option.feasible:
            exclusions.append(
                CandidateExclusion(
                    candidate_id=candidate_id,
                    supplier_id=option.supplier_id,
                    reasons=list(option.reasons),
                )
            )
            continue
        projection = project_cash(state, option.total_cost_rupees)
        if not projection.feasible:
            exclusions.append(
                CandidateExclusion(
                    candidate_id=candidate_id,
                    supplier_id=option.supplier_id,
                    reasons=["cash_buffer_breached"],
                    details={
                        "ending_cash_rupees": str(projection.ending_cash_rupees),
                        "minimum_buffer_rupees": str(projection.minimum_buffer_rupees),
                    },
                )
            )
            continue
        plans.append(
            _build_plan(
                orders,
                state.state_version,
                sku_id,
                immediate_available_units,
                option,
                planning_horizon,
                projection,
            )
        )
    return plans, exclusions


def build_view_candidate_plans(
    view: PlanningView,
    supplier_options: list[SupplierOption],
    receipt_timing: str = "actual",
) -> tuple[list[CandidatePlan], list[CandidateExclusion]]:
    def projection(outflow: Decimal) -> CashProjection:
        return project_dated_cash(
            view.opening_cash_rupees,
            view.state.minimum_cash_buffer_rupees,
            outflow,
            view.receipts,
            view.state.as_of.date(),
            view.planning_horizon,
            receipt_timing,
        )

    stock_cash = projection(Decimal("0.00"))
    stock_plan = _build_plan(
        view.orders,
        view.state.state_version,
        view.sku_id,
        view.immediate_available_units,
        None,
        view.planning_horizon,
        stock_cash,
    )
    plans = []
    exclusions = []
    if stock_cash.feasible:
        plans.append(stock_plan)
    else:
        exclusions.append(
            CandidateExclusion(
                candidate_id="stock-only",
                reasons=["cash_buffer_breached"],
                details={
                    "ending_cash_rupees": str(stock_cash.ending_cash_rupees),
                    "minimum_buffer_rupees": str(stock_cash.minimum_buffer_rupees),
                },
            )
        )
    for option in supplier_options:
        candidate_id = f"supplier-{option.supplier_id}"
        if not option.feasible:
            exclusions.append(
                CandidateExclusion(
                    candidate_id=candidate_id,
                    supplier_id=option.supplier_id,
                    reasons=list(option.reasons),
                )
            )
            continue
        cash = projection(option.total_cost_rupees)
        if not cash.feasible:
            exclusions.append(
                CandidateExclusion(
                    candidate_id=candidate_id,
                    supplier_id=option.supplier_id,
                    reasons=["cash_buffer_breached"],
                    details={
                        "ending_cash_rupees": str(cash.ending_cash_rupees),
                        "minimum_buffer_rupees": str(cash.minimum_buffer_rupees),
                    },
                )
            )
            continue
        plans.append(
            _build_plan(
                view.orders,
                view.state.state_version,
                view.sku_id,
                view.immediate_available_units,
                option,
                view.planning_horizon,
                cash,
            )
        )
    return plans, exclusions


def rank_key(plan: CandidatePlan) -> tuple:
    """Published objective: unmet, then late, then arrival, then cost in paise, then id.

    A stock-only plan has no arrival date, so it sorts after every dated supplier arrival.
    Cost is integer paise so this key matches the OR-Tools model exactly.
    """
    option = plan.supplier_option
    arrival = option.scenario_arrival_date.toordinal() if option else date.max.toordinal()
    cost_paise = int((plan.total_cost_rupees * 100).to_integral_value())
    return (plan.unmet_units, plan.late_units, arrival, cost_paise, plan.candidate_id)


def select_best_plan(plans: list[CandidatePlan]) -> CandidatePlan:
    if not plans:
        raise ValueError("No candidate plans are available")
    return min(plans, key=rank_key)
