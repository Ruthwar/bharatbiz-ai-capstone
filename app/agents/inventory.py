from app.schemas.contracts import AgentResult, BusinessState


def available_units(on_hand: int, reserved: int, incoming: int = 0) -> int:
    return max(0, on_hand - reserved + incoming)


def reorder_flag(on_hand: int, reorder_point: int) -> bool:
    return on_hand <= reorder_point


def analyze_inventory(state: BusinessState, sku_id: str, delayed_incoming_units: int) -> AgentResult:
    row = next((item for item in state.inventory if item["sku_id"] == sku_id), None)
    if row is None:
        raise ValueError(f"Unknown inventory SKU: {sku_id}")
    if delayed_incoming_units < 0 or delayed_incoming_units > row["incoming_units"]:
        raise ValueError("Delayed incoming units must be between zero and the available incoming quantity")

    before_delay = available_units(row["on_hand_units"], row["reserved_units"], row["incoming_units"])
    immediate = available_units(
        row["on_hand_units"], row["reserved_units"], row["incoming_units"] - delayed_incoming_units
    )
    assumption = (
        f"For this simulation, {delayed_incoming_units} incoming {row['unit']} units are unavailable "
        "until the delayed supplier arrival."
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
            "delayed_incoming_units": delayed_incoming_units,
            "available_before_delay_units": before_delay,
            "immediately_available_units": immediate,
            "reorder_required": reorder_flag(row["on_hand_units"], row["reorder_point_units"]),
        },
        evidence_refs=[f"inventory:{sku_id}", state.state_version],
        assumptions=[assumption],
    )
