from datetime import date

from app.schemas.contracts import AgentResult, BusinessState
from app.schemas.retail import FulfilmentResult, OrderAllocation, SkuFulfilment

PRIORITY_RANK = {"high": 0, "normal": 1}
FULFILMENT_RULE = "order priority, requested delivery date, retailer service priority, order date, order id"


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


def available_by_sku(state: BusinessState, include_incoming: bool = False) -> dict[str, int]:
    available = {}
    for row in state.inventory:
        units = row["on_hand_units"] - row["reserved_units"]
        if include_incoming:
            units += row["incoming_units"]
        available[row["sku_id"]] = max(0, units)
    return available


def service_key(order: dict, retailers: dict[str, dict]) -> tuple:
    retailer = retailers.get(order["retailer_id"], {})
    return (
        PRIORITY_RANK.get(order.get("priority", "normal"), 1),
        order["requested_delivery_date"],
        PRIORITY_RANK.get(retailer.get("service_priority", "normal"), 1),
        order["order_date"],
        order["order_id"],
    )


def prioritised_open_orders(state: BusinessState, sku_id: str | None = None) -> list[dict]:
    retailers = {row["retailer_id"]: row for row in state.retailers}
    rows = [
        row
        for row in state.open_orders
        if row["status"] == "open" and (sku_id is None or row["sku_id"] == sku_id)
    ]
    return sorted(rows, key=lambda row: service_key(row, retailers))


def _fulfilment_status(allocated: int, requested: int) -> str:
    if requested and allocated >= requested:
        return "full"
    return "partial" if allocated else "unfulfilled"


def _expected_units(state: BusinessState) -> dict[str, str]:
    return {row["sku_id"]: row["base_unit"] for row in state.products}


def allocate_by_priority(
    state: BusinessState,
    sku_id: str | None = None,
    available: dict[str, int] | None = None,
    include_incoming: bool = False,
) -> list[OrderAllocation]:
    stock = dict(available if available is not None else available_by_sku(state, include_incoming))
    retailers = {row["retailer_id"]: row for row in state.retailers}
    expected_units = _expected_units(state)
    as_of = state.as_of.date()
    rank_by_sku: dict[str, int] = {}
    rows = []
    for order in prioritised_open_orders(state, sku_id):
        sku = order["sku_id"]
        requested = order["quantity_units"]
        if order["unit"] == expected_units.get(sku):
            allocated, unmet = fill_order(requested, stock.get(sku, 0))
            stock[sku] = stock.get(sku, 0) - allocated
        else:
            allocated, unmet = 0, requested
        rank_by_sku[sku] = rank_by_sku.get(sku, 0) + 1
        due = date.fromisoformat(order["requested_delivery_date"])
        rows.append(
            OrderAllocation(
                order_id=order["order_id"],
                retailer_id=order["retailer_id"],
                retailer_name=retailers.get(order["retailer_id"], {}).get("retailer_name", ""),
                sku_id=sku,
                unit=order["unit"],
                priority=order.get("priority", "normal"),
                requested_delivery_date=due,
                requested_units=requested,
                allocated_units=allocated,
                unmet_units=unmet,
                status=_fulfilment_status(allocated, requested),
                fill_rate=round(allocated / requested, 4) if requested else 1.0,
                overdue=due < as_of,
                service_rank=rank_by_sku[sku],
            )
        )
    return rows


def allocate_fifo_view(state: BusinessState, available: dict[str, int]) -> dict[str, int]:
    stock = dict(available)
    allocations = {}
    expected_units = _expected_units(state)
    orders = sorted(
        (row for row in state.open_orders if row["status"] == "open"),
        key=lambda row: (row["order_date"], row["order_id"]),
    )
    for order in orders:
        if order["unit"] != expected_units.get(order["sku_id"]):
            allocations[order["order_id"]] = 0
            continue
        allocated, _ = fill_order(order["quantity_units"], stock.get(order["sku_id"], 0))
        stock[order["sku_id"]] = stock.get(order["sku_id"], 0) - allocated
        allocations[order["order_id"]] = allocated
    return allocations


def verify_allocation(
    state: BusinessState,
    rows: list[OrderAllocation],
    available: dict[str, int],
) -> list[str]:
    violations = []
    orders = {row["order_id"]: row for row in state.open_orders}
    expected_units = _expected_units(state)
    used: dict[str, int] = {}
    seen = set()
    for row in rows:
        if row.order_id in seen:
            violations.append(f"duplicate_allocation:{row.order_id}")
        seen.add(row.order_id)
        order = orders.get(row.order_id)
        if order is None:
            violations.append(f"unknown_order:{row.order_id}")
            continue
        if order["sku_id"] != row.sku_id:
            violations.append(f"sku_mismatch:{row.order_id}")
        if order["unit"] != row.unit:
            violations.append(f"unit_converted:{row.order_id}")
        if row.unit != expected_units.get(row.sku_id):
            violations.append(f"incompatible_unit:{row.order_id}")
        if order["quantity_units"] != row.requested_units:
            violations.append(f"requested_quantity_mismatch:{row.order_id}")
        if row.allocated_units + row.unmet_units != row.requested_units:
            violations.append(f"allocation_conservation_failed:{row.order_id}")
        if row.allocated_units > row.requested_units:
            violations.append(f"over_allocated:{row.order_id}")
        used[row.sku_id] = used.get(row.sku_id, 0) + row.allocated_units
    for sku, total in used.items():
        if total > available.get(sku, 0):
            violations.append(f"stock_exceeded:{sku}")
    return violations


def analyze_fulfilment(
    state: BusinessState,
    sku_id: str | None = None,
    include_incoming: bool = False,
) -> FulfilmentResult:
    available = available_by_sku(state, include_incoming)
    rows = allocate_by_priority(state, sku_id, available)
    inventory_units = {row["sku_id"]: row["unit"] for row in state.inventory}
    by_sku = []
    for sku in sorted({row.sku_id for row in rows}):
        sku_rows = [row for row in rows if row.sku_id == sku]
        requested = sum(row.requested_units for row in sku_rows)
        allocated = sum(row.allocated_units for row in sku_rows)
        by_sku.append(
            SkuFulfilment(
                sku_id=sku,
                unit=inventory_units.get(sku, sku_rows[0].unit),
                available_units=available.get(sku, 0),
                requested_units=requested,
                allocated_units=allocated,
                unmet_units=requested - allocated,
                fill_rate=round(allocated / requested, 4) if requested else 1.0,
                free_after_allocation_units=max(0, available.get(sku, 0) - allocated),
            )
        )
    fifo = allocate_fifo_view(state, available)
    changed = [
        {
            "order_id": row.order_id,
            "priority": row.priority,
            "priority_rule_units": row.allocated_units,
            "fifo_units": fifo.get(row.order_id, 0),
        }
        for row in rows
        if fifo.get(row.order_id, 0) != row.allocated_units
    ]
    total_requested = sum(row.requested_units for row in rows)
    return FulfilmentResult(
        state_version=state.state_version,
        as_of=state.as_of.date(),
        rule=FULFILMENT_RULE,
        include_incoming=include_incoming,
        allocations=rows,
        by_sku=by_sku,
        fill_rate=round(sum(row.allocated_units for row in rows) / total_requested, 4) if total_requested else 1.0,
        changed_vs_fifo=changed,
        verification_violations=verify_allocation(state, rows, available),
    )
