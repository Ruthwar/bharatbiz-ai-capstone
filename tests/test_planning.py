from datetime import date
from decimal import Decimal

from app.agents.inventory import analyze_inventory
from app.agents.orders import analyze_orders
from app.agents.supplier import build_supplier_options
from app.optimization.baseline import build_candidate_plans, select_best_plan
from app.verification.checks import verify_plan


def _selected_plan(state):
    inventory = analyze_inventory(state, "SKU-003", 12)
    orders = analyze_orders(state, "SKU-003")
    options = build_supplier_options(state, "SKU-003", 46, "SUP-005", 2, date(2026, 11, 26))
    plans = build_candidate_plans(state, "SKU-003", 56, options, date(2026, 11, 26))
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
