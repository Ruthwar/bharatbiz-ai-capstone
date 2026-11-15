"""Unit tests for the inventory agent.

Owner: Saurabh.
Covers:
  - normal case (healthy stock, no shortage)
  - shortage case (delayed incoming creates a gap)
  - discrepancy case (impossible input rejected, not silently clamped)
"""

from datetime import date, datetime, timezone

import pytest

from app.agents.inventory import (
    analyze_inventory,
    available_to_promise,
    available_units,
    demand_baseline,
    inventory_position,
    reorder_flag,
    shortage_units,
)
from app.schemas.contracts import BusinessState


def make_state(inventory_rows, open_orders=None) -> BusinessState:
    return BusinessState(
        as_of=datetime(2026, 1, 5, tzinfo=timezone.utc),
        state_version="state-v1",
        cash_balance_rupees=100_000,
        minimum_cash_buffer_rupees=20_000,
        inventory=inventory_rows,
        open_orders=open_orders or [],
        products=[],
        retailers=[],
        suppliers=[],
        supplier_offers=[],
    )


# ---------- Pure helpers ----------

def test_available_units_never_negative():
    assert available_units(10, 3) == 7
    assert available_units(3, 10) == 0


def test_available_to_promise_includes_incoming():
    assert available_to_promise(10, 3, 5) == 12
    assert available_to_promise(0, 0, 4) == 4


def test_inventory_position_uses_spec_formula():
    # Spec §6.1: on_hand - reserved + confirmed_incoming
    assert inventory_position(10, 3, 5) == 12


def test_reorder_flag_boundary():
    assert reorder_flag(5, 5) is True
    assert reorder_flag(6, 5) is False


def test_shortage_units_never_negative():
    assert shortage_units(10, 3) == 0
    assert shortage_units(3, 10) == 7


def test_demand_baseline_sums_only_open_orders():
    orders = [
        {"order_id": "O1", "sku_id": "SKU-1", "quantity_units": 5, "status": "open"},
        {"order_id": "O2", "sku_id": "SKU-1", "quantity_units": 7, "status": "open"},
        {"order_id": "O3", "sku_id": "SKU-1", "quantity_units": 4, "status": "closed"},
        {"order_id": "O4", "sku_id": "SKU-2", "quantity_units": 9, "status": "open"},
    ]
    assert demand_baseline(orders, "SKU-1") == 12


# ---------- Normal case ----------

def test_normal_case_no_shortage_no_reorder():
    state = make_state(
        inventory_rows=[
            {
                "sku_id": "SKU-1",
                "on_hand_units": 100,
                "reserved_units": 20,
                "incoming_units": 50,
                "reorder_point_units": 30,
                "unit": "case",
            }
        ],
        open_orders=[
            {"order_id": "O1", "sku_id": "SKU-1", "quantity_units": 30, "status": "open"},
        ],
    )
    result = analyze_inventory(state, "SKU-1")

    p = result.proposal
    assert p["available_units"] == 80           # 100 - 20
    assert p["atp_units"] == 130                # 100 - 20 + 50
    assert p["open_demand_units"] == 30
    assert p["shortage_units"] == 0
    assert p["reorder_required"] is False
    assert p["expiry_risk"] is False
    assert result.status == "ok"
    assert result.state_version == "state-v1"


# ---------- Shortage case (your required scenario) ----------

def test_shortage_case_with_delayed_incoming():
    """Delayed supplier arrival turns ATP into a gap. This is the demo scenario."""
    state = make_state(
        inventory_rows=[
            {
                "sku_id": "SKU-1",
                "on_hand_units": 40,
                "reserved_units": 10,
                "incoming_units": 50,
                "reorder_point_units": 20,
                "unit": "case",
            }
        ],
        open_orders=[
            {"order_id": "O1", "sku_id": "SKU-1", "quantity_units": 70, "status": "open"},
        ],
    )

    # Without delay: ATP 80 covers demand 70, no shortage
    base = analyze_inventory(state, "SKU-1")
    assert base.proposal["atp_units"] == 80
    assert base.proposal["shortage_units"] == 0

    # Delay 40 of the 50 incoming -> immediately available drops to 40
    delayed = analyze_inventory(state, "SKU-1", delayed_incoming_units=40)
    p = delayed.proposal
    assert p["immediately_available_units"] == 40
    assert p["open_demand_units"] == 70
    # ATP (80) still covers demand (70) because 10 units of incoming remain
    # undelayed, so the long-term shortage is zero.
    assert p["shortage_units"] == 0
    # The real "immediately unmet" gap — what the demo actually shows — is
    # demand minus immediately available stock.
    assert p["open_demand_units"] - p["immediately_available_units"] == 30
    assert any("unavailable" in a for a in delayed.assumptions)


def test_shortage_against_immediately_available():
    """Separate check: shortfall vs. immediately usable stock."""
    state = make_state(
        inventory_rows=[
            {
                "sku_id": "SKU-1",
                "on_hand_units": 40,
                "reserved_units": 10,
                "incoming_units": 50,
                "reorder_point_units": 20,
                "unit": "case",
            }
        ],
        open_orders=[
            {"order_id": "O1", "sku_id": "SKU-1", "quantity_units": 70, "status": "open"},
        ],
    )
    delayed = analyze_inventory(state, "SKU-1", delayed_incoming_units=50)
    p = delayed.proposal
    # immediately_available = 40 - 10 + (50 - 50) = 30
    assert p["immediately_available_units"] == 30
    assert p["open_demand_units"] == 70
    # There is still a gap between demand and what is truly on hand
    assert p["open_demand_units"] - p["immediately_available_units"] == 40


# ---------- Discrepancy / missing data cases ----------

def test_rejects_negative_on_hand():
    state = make_state(
        inventory_rows=[
            {
                "sku_id": "SKU-1",
                "on_hand_units": -5,
                "reserved_units": 0,
                "incoming_units": 0,
                "reorder_point_units": 0,
                "unit": "case",
            }
        ]
    )
    with pytest.raises(ValueError, match="Negative on-hand"):
        analyze_inventory(state, "SKU-1")


def test_rejects_reserved_greater_than_on_hand():
    state = make_state(
        inventory_rows=[
            {
                "sku_id": "SKU-1",
                "on_hand_units": 5,
                "reserved_units": 10,
                "incoming_units": 0,
                "reorder_point_units": 0,
                "unit": "case",
            }
        ]
    )
    with pytest.raises(ValueError, match="Reserved exceeds on-hand"):
        analyze_inventory(state, "SKU-1")


def test_unknown_sku_raises():
    state = make_state(inventory_rows=[])
    with pytest.raises(ValueError, match="Unknown inventory SKU"):
        analyze_inventory(state, "SKU-MISSING")


def test_missing_expiry_reports_unmet_data_warning():
    state = make_state(
        inventory_rows=[
            {
                "sku_id": "SKU-1",
                "on_hand_units": 10,
                "reserved_units": 0,
                "incoming_units": 0,
                "reorder_point_units": 5,
                "unit": "case",
                # no expiry_date, no warehouse_capacity_units
            }
        ]
    )
    result = analyze_inventory(state, "SKU-1")
    joined = " ".join(result.assumptions)
    assert "No expiry_date" in joined
    assert "No warehouse_capacity_units" in joined


def test_delayed_incoming_out_of_bounds_rejected():
    state = make_state(
        inventory_rows=[
            {
                "sku_id": "SKU-1",
                "on_hand_units": 10,
                "reserved_units": 0,
                "incoming_units": 5,
                "reorder_point_units": 0,
                "unit": "case",
            }
        ]
    )
    with pytest.raises(ValueError):
        analyze_inventory(state, "SKU-1", delayed_incoming_units=6)

def test_expiry_date_handling_does_not_crash():
    """Ensure datetime vs date subtraction works (Issue 3 fix)."""
    state = make_state(
        inventory_rows=[
            {
                "sku_id": "SKU-EXP",
                "on_hand_units": 10,
                "reserved_units": 0,
                "incoming_units": 0,
                "reorder_point_units": 5,
                "unit": "case",
                "expiry_date": "2026-01-10", # Exactly 5 days from as_of
            }
        ]
    )
    # as_of in make_state is datetime(2026, 1, 5, tzinfo=timezone.utc)
    # This should not raise TypeError
    result = analyze_inventory(state, "SKU-EXP", planning_horizon_days=7)
    assert result.proposal["expiry_risk"] is True

def test_immediate_shortage_units_logic():
    """Ensure immediate_shortage_units captures the gap created by delays (Issue 2 fix)."""
    state = make_state(
        inventory_rows=[
            {
                "sku_id": "SKU-1",
                "on_hand_units": 40,
                "reserved_units": 10,
                "incoming_units": 50,
                "reorder_point_units": 20,
                "unit": "case",
            }
        ],
        open_orders=[
            {"order_id": "O1", "sku_id": "SKU-1", "quantity_units": 70, "status": "open"},
        ],
    )
    # Delay 40 of 50 incoming -> ATP is 80 (no long-term shortage), but immediate available is 40.
    delayed = analyze_inventory(state, "SKU-1", delayed_incoming_units=40)
    
    assert delayed.proposal["shortage_units"] == 0
    assert delayed.proposal["immediate_shortage_units"] == 30 # 70 demand - 40 immediate