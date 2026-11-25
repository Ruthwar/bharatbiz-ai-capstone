from decimal import Decimal

import pytest

from app.state import StateVersionMismatch, load_business_state


def test_loads_versioned_operational_state(state):
    assert state.state_version == "synthetic-v3-live-20261123"
    assert len(state.products) == 12
    assert len(state.inventory) == 12
    assert len(state.open_orders) == 30
    assert len(state.suppliers) == 5
    assert state.cash_balance_rupees == Decimal("250000.00")
    assert state.as_of.isoformat() == "2026-11-23T00:00:00+05:30"


def test_rejects_state_version_mismatch():
    with pytest.raises(StateVersionMismatch):
        load_business_state(expected_version="sim-v1")
