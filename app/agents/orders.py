from app.schemas.contracts import AgentResult, BusinessState


def fill_order(requested: int, available: int) -> tuple[int, int]:
    fulfilled = min(max(requested, 0), max(available, 0))
    return fulfilled, max(requested - fulfilled, 0)


def affected_orders(state: BusinessState, sku_id: str) -> list[dict]:
    return sorted(
        (row for row in state.open_orders if row["sku_id"] == sku_id and row["status"] == "open"),
        key=lambda row: (row["order_date"], row["order_id"]),
    )


def analyze_orders(state: BusinessState, sku_id: str) -> AgentResult:
    retailers = {row["retailer_id"]: row for row in state.retailers}
    orders = [
        {
            **row,
            "retailer_name": retailers.get(row["retailer_id"], {}).get("retailer_name", ""),
            "area": retailers.get(row["retailer_id"], {}).get("area", ""),
        }
        for row in affected_orders(state, sku_id)
    ]
    return AgentResult(
        agent_name="orders",
        status="ok",
        state_version=state.state_version,
        proposal={
            "sku_id": sku_id,
            "affected_orders": orders,
            "affected_order_count": len(orders),
            "total_requested_units": sum(row["quantity_units"] for row in orders),
            "unit": orders[0]["unit"] if orders else None,
        },
        evidence_refs=[f"order:{row['order_id']}" for row in orders],
    )
