from datetime import date
from decimal import Decimal

import pytest

from app.agents.cashflow import projected_cash
from app.agents.inventory import analyze_inventory
from app.agents.orders import analyze_orders
from app.agents.supplier import build_supplier_options


def test_inventory_and_order_impact(state):
    inventory = analyze_inventory(state, "SKU-003", 12)
    orders = analyze_orders(state, "SKU-003")

    assert inventory.proposal["atp_units"] == 68
    assert inventory.proposal["immediately_available_units"] == 56
    assert orders.proposal["affected_order_count"] == 6
    assert orders.proposal["total_requested_units"] == 102


def test_supplier_options_use_listed_offers_and_scenario_delay(state):
    options = build_supplier_options(state, "SKU-003", 46, "SUP-005", 2, date(2026, 11, 26))

    assert [option.supplier_id for option in options] == ["SUP-002", "SUP-003", "SUP-005"]
    assert all(option.feasible for option in options)
    original = options[-1]
    assert original.lead_time_days == 3
    assert original.scenario_arrival_date == date(2026, 11, 26)


def test_cash_rejects_negative_outflow_magnitude():
    with pytest.raises(ValueError, match="non-negative"):
        projected_cash(
            Decimal("250000.00"),
            Decimal("0.00"),
            Decimal("-5965.76"),
            Decimal("50000.00"),
        )
