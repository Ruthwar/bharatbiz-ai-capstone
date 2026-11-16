from datetime import date
from decimal import Decimal

from app.agents.inventory import analyze_inventory
from app.agents.orders import analyze_orders
from app.agents.supplier import build_supplier_options
from app.optimization.baseline import build_candidate_plans, rank_key, select_best_plan
from app.optimization.negotiation import negotiate
from app.optimization.ortools_selector import select_best_plan_ortools
from app.schemas.contracts import CandidatePlan, CashProjection, SupplierOption
from app.verification.checks import verify_inventory_identity, verify_plan


def _selected_plan(state):
    inventory = analyze_inventory(state, "SKU-003", 12)
    orders = analyze_orders(state, "SKU-003")
    options = build_supplier_options(state, "SKU-003", 46, "SUP-005", 2, date(2026, 11, 4))
    plans, _exclusions = build_candidate_plans(state, "SKU-003", 56, options, date(2026, 11, 4))
    return inventory, orders, plans, select_best_plan(plans)


def test_selects_repeatable_verified_supplier_plan(state):
    _, _, plans, selected = _selected_plan(state)

    assert plans[0].candidate_id == "stock-only"
    assert plans[0].fulfilled_units == 56
    assert plans[0].unmet_units == 46
    assert selected.candidate_id == "supplier-SUP-002"
    assert selected.fulfilled_units == 102
    assert selected.late_units == 28
    assert selected.unmet_units == 0
    assert selected.total_cost_rupees == Decimal("4876.46")
    assert selected.cash_projection.ending_cash_rupees == Decimal("245123.54")
    assert verify_plan(state, selected, 56).valid


def test_verifier_rejects_stock_overallocation(state):
    _, _, _, selected = _selected_plan(state)
    corrupted = selected.model_copy(deep=True)
    corrupted.allocations[0].stock_fulfilled_units += 1

    result = verify_plan(state, corrupted, 56)

    assert not result.valid
    assert "stock_exceeded:SKU-003" in result.violations


def test_verifier_rejects_cash_buffer_breach(state):
    _, _, _, selected = _selected_plan(state)
    low_cash_state = state.model_copy(update={"cash_balance_rupees": Decimal("54876.45")})
    candidate = selected.model_copy(deep=True)
    candidate.cash_projection.ending_cash_rupees = Decimal("49999.99")
    candidate.cash_projection.headroom_rupees = Decimal("-0.01")
    candidate.cash_projection.feasible = False

    result = verify_plan(low_cash_state, candidate, 56)

    assert not result.valid
    assert result.violations == ["minimum_cash_buffer_breached"]


def _cash() -> CashProjection:
    return CashProjection(
        ending_cash_rupees=Decimal("100000.00"),
        minimum_buffer_rupees=Decimal("50000.00"),
        headroom_rupees=Decimal("50000.00"),
        feasible=True,
    )


def _option(supplier_id: str, arrival: date, cost: str) -> SupplierOption:
    return SupplierOption(
        supplier_id=supplier_id,
        sku_id="SKU-003",
        quantity_units=10,
        unit_cost_rupees=Decimal(cost),
        total_cost_rupees=Decimal(cost),
        lead_time_days=1,
        scenario_arrival_date=arrival,
        min_order_units=1,
        capacity_units=20,
        feasible=True,
    )


def _plan(candidate_id: str, unmet: int, late: int, cost: str, option: SupplierOption | None) -> CandidatePlan:
    return CandidatePlan(
        candidate_id=candidate_id,
        state_version="synthetic-v2-seed-20261105",
        planning_horizon=date(2026, 11, 4),
        supplier_option=option,
        allocations=[],
        total_requested_units=10,
        fulfilled_units=10 - unmet,
        late_units=late,
        unmet_units=unmet,
        total_cost_rupees=Decimal(cost),
        cash_projection=_cash(),
    )


def test_ortools_uses_the_same_objective_as_deterministic_ranking():
    early_expensive = _plan(
        "supplier-SUP-002",
        0,
        0,
        "90.00",
        _option("SUP-002", date(2026, 11, 2), "90.00"),
    )
    late_cheap = _plan(
        "supplier-SUP-005",
        0,
        4,
        "40.00",
        _option("SUP-005", date(2026, 11, 4), "40.00"),
    )
    stock_only = _plan("stock-only", 3, 0, "0.00", None)

    plans = [stock_only, late_cheap, early_expensive]
    assert select_best_plan(plans).candidate_id == "supplier-SUP-002"
    chosen, status = select_best_plan_ortools(plans)
    assert status == "OPTIMAL"
    assert chosen.candidate_id == "supplier-SUP-002"
    assert rank_key(chosen) == rank_key(select_best_plan(plans))


def test_empty_candidate_set_is_infeasible_for_both_planners():
    agreement = negotiate([])
    assert agreement.status == "infeasible"
    assert agreement.planners_agree is True
    assert agreement.ortools_status == "INFEASIBLE"
    assert agreement.selected is None


def test_short_cash_excludes_stock_only_and_supplier_purchases(state):
    low_cash = state.model_copy(update={"cash_balance_rupees": Decimal("40000.00")})
    options = build_supplier_options(low_cash, "SKU-003", 46, "SUP-005", 2, date(2026, 11, 4))
    plans, exclusions = build_candidate_plans(low_cash, "SKU-003", 56, options, date(2026, 11, 4))
    reasons = {row.candidate_id: row.reasons for row in exclusions}

    assert plans == []
    assert reasons["stock-only"] == ["cash_buffer_breached"]
    assert reasons["supplier-SUP-002"] == ["cash_buffer_breached"]
    agreement = negotiate(plans, exclusions)
    assert agreement.status == "infeasible"
    assert agreement.selected is None


def test_inventory_identity_rejects_a_mismatched_atp():
    assert verify_inventory_identity(10, 2, 5, 13, 0) == []
    assert "atp_identity_failed" in verify_inventory_identity(10, 2, 5, 99, 0)
    assert "negative_shortage" in verify_inventory_identity(10, 2, 5, 13, -1)
