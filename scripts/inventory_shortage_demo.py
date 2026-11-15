"""Reproducible shortage demo for the inventory agent.

Run (from the project root):
    python scripts/inventory_shortage_demo.py
"""

from datetime import datetime, timezone
import json
import sys
from pathlib import Path

# Make `app` importable when running this script directly.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.agents.inventory import analyze_inventory
from app.schemas.contracts import BusinessState

def build_demo_state() -> BusinessState:
    return BusinessState(
        as_of=datetime(2026, 1, 5, tzinfo=timezone.utc),
        state_version="demo-state-v1",
        cash_balance_rupees=100_000,
        minimum_cash_buffer_rupees=20_000,
        inventory=[
            {
                "sku_id": "SKU-DEMO-1",
                "on_hand_units": 40,
                "reserved_units": 10,
                "incoming_units": 50,
                "reorder_point_units": 20,
                "unit": "case",
            }
        ],
        open_orders=[
            {
                "order_id": "ORD-DEMO-1",
                "sku_id": "SKU-DEMO-1",
                "quantity_units": 70,
                "status": "open",
            }
        ],
        products=[],
        retailers=[],
        suppliers=[],
        supplier_offers=[],
    )


def main() -> None:
    state = build_demo_state()

    print("=== Before delay ===")
    before = analyze_inventory(state, "SKU-DEMO-1")
    print(json.dumps(before.proposal, indent=2))
    print("Assumptions:", before.assumptions)

    print("\n=== After supplier delay (40 of 50 incoming delayed) ===")
    after = analyze_inventory(state, "SKU-DEMO-1", delayed_incoming_units=40)
    print(json.dumps(after.proposal, indent=2))
    print("Assumptions:", after.assumptions)


if __name__ == "__main__":
    main()