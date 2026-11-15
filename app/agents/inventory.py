"""Inventory & demand analysis agent (deterministic).

Owner: Saurabh.
Scope:
- Inventory position (on-hand, reserved, incoming, available, ATP)
- Reorder flag and shortage indicators
- Simple demand baseline from open orders
- Delayed-incoming (shortage) scenario
- No LLM arithmetic: every number here is computed from the state.

Contract guarantees:
- Raises ValueError on impossible input (negative on-hand, reserved > on-hand, etc.)
- Never returns negative available or ATP.
- Every result carries state_version and evidence_refs.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from app.schemas.contracts import AgentResult, BusinessState


ZERO = Decimal("0.00")


# ---------- Pure helpers (unit-testable) ----------

def _validate_row(row: dict) -> None:
    """Reject impossible inventory records instead of silently clamping."""
    required = ("sku_id", "on_hand_units", "reserved_units", "incoming_units", "reorder_point_units", "unit")
    missing = [k for k in required if k not in row]
    if missing:
        raise ValueError(f"Inventory row missing fields: {missing}")
    if row["on_hand_units"] < 0:
        raise ValueError(f"Negative on-hand for {row['sku_id']}: {row['on_hand_units']}")
    if row["reserved_units"] < 0:
        raise ValueError(f"Negative reserved for {row['sku_id']}: {row['reserved_units']}")
    if row["incoming_units"] < 0:
        raise ValueError(f"Negative incoming for {row['sku_id']}: {row['incoming_units']}")
    if row["reorder_point_units"] < 0:
        raise ValueError(f"Negative reorder point for {row['sku_id']}: {row['reorder_point_units']}")
    if row["reserved_units"] > row["on_hand_units"]:
        raise ValueError(
            f"Reserved exceeds on-hand for {row['sku_id']}: "
            f"reserved={row['reserved_units']} > on_hand={row['on_hand_units']}"
        )


def available_units(on_hand: int, reserved: int) -> int:
    """Physical stock that is free to allocate right now (no incoming)."""
    return max(0, on_hand - reserved)


def available_to_promise(on_hand: int, reserved: int, incoming: int = 0) -> int:
    """ATP = available now + confirmed incoming. Never negative."""
    return max(0, on_hand - reserved + incoming)


def inventory_position(on_hand: int, reserved: int, confirmed_incoming: int) -> int:
    """Spec §6.1: on_hand - reserved + confirmed_incoming."""
    return on_hand - reserved + confirmed_incoming


def reorder_flag(on_hand: int, reorder_point: int) -> bool:
    """Reorder is required when on-hand at or below the configured point."""
    return on_hand <= reorder_point


def shortage_units(available: int, open_demand: int) -> int:
    """Shortfall vs. current open demand. Non-negative."""
    return max(0, open_demand - available)


def demand_baseline(open_orders: list[dict], sku_id: str) -> int:
    """Simple demand baseline: sum of open order quantities for this SKU."""
    return sum(
        int(order["quantity_units"])
        for order in open_orders
        if order["sku_id"] == sku_id and order.get("status") == "open"
    )


def is_expiring(expiry_date: str | None, as_of: date, horizon_days: int) -> bool:
    """Expiry check where simulated data supplies an expiry_date."""
    if not expiry_date:
        return False
    try:
        exp = date.fromisoformat(expiry_date)
    except ValueError:
        return False
    return (exp - as_of).days <= horizon_days


# ---------- Agent entry point ----------

def analyze_inventory(
    state: BusinessState,
    sku_id: str,
    delayed_incoming_units: int = 0,
    planning_horizon_days: int = 14,
) -> AgentResult:
    """Full inventory analysis for one SKU.

    Returns an AgentResult with:
      proposal:
        sku_id, unit,
        on_hand_units, reserved_units, incoming_units,
        available_units, atp_units,
        delayed_incoming_units, immediately_available_units,
        open_demand_units, shortage_units,
        reorder_required,
        expiry_risk (bool)
      assumptions: any warnings, including unmet-data warnings
    Raises ValueError on impossible input. Never returns negative availability.
    """
    row = next((item for item in state.inventory if item["sku_id"] == sku_id), None)
    if row is None:
        raise ValueError(f"Unknown inventory SKU: {sku_id}")

    _validate_row(row)

    if delayed_incoming_units < 0 or delayed_incoming_units > row["incoming_units"]:
        raise ValueError(
            "Delayed incoming units must be between zero and the available incoming quantity"
        )

    # Demand baseline from open orders (this is Rajesh's data, read-only here)
    open_demand = demand_baseline(state.open_orders, sku_id)

    # Availability chain
    available_now = available_units(row["on_hand_units"], row["reserved_units"])
    atp = available_to_promise(
        row["on_hand_units"], row["reserved_units"], row["incoming_units"]
    )
    immediately_available = available_to_promise(
        row["on_hand_units"],
        row["reserved_units"],
        row["incoming_units"] - delayed_incoming_units,
    )
    shortfall = shortage_units(atp, open_demand)
    immediate_shortfall = shortage_units(immediately_available, open_demand)

    # Reorder decision
    reorder = reorder_flag(row["on_hand_units"], row["reorder_point_units"])

    # Expiry check (only when the field exists)
    expiry_date = row.get("expiry_date")
    as_of_date = state.as_of.date() if hasattr(state.as_of, "date") else state.as_of
    expiry_risk = is_expiring(expiry_date, as_of_date, planning_horizon_days)

    # Assumptions and unmet-data warnings
    assumptions: list[str] = []
    if delayed_incoming_units > 0:
        assumptions.append(
            f"{delayed_incoming_units} incoming {row['unit']} units of {sku_id} "
            "are unavailable until the delayed supplier arrival."
        )
    if row.get("expiry_date") is None:
        assumptions.append(
            f"No expiry_date supplied for {sku_id}; expiry risk not assessed."
        )
    if row.get("warehouse_capacity_units") is None:
        assumptions.append(
            f"No warehouse_capacity_units supplied; capacity check skipped for {sku_id}."
        )

    return AgentResult(
        agent_name="inventory",
        status="ok",
        state_version=state.state_version,
        proposal={
            "sku_id": sku_id,
            "unit": row["unit"],
            "on_hand_units": row["on_hand_units"],
            "reserved_units": row["reserved_units"],
            "incoming_units": row["incoming_units"],
            "available_units": available_now,
            "atp_units": atp,
            "delayed_incoming_units": delayed_incoming_units,
            "immediately_available_units": immediately_available,
            "open_demand_units": open_demand,
            "shortage_units": shortfall,
            "immediate_shortage_units": immediate_shortfall,
            "reorder_required": reorder,
            "reorder_point_units": row["reorder_point_units"],
            "expiry_risk": expiry_risk,
        },
        evidence_refs=[f"inventory:{sku_id}", state.state_version],
        assumptions=assumptions,
    )