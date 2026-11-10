from datetime import date, timedelta

from app.schemas.contracts import BusinessState, SupplierOption


def supplier_is_feasible(quantity: int, minimum_order: int, capacity: int, lead_days: int, latest_day: int) -> bool:
    return quantity >= minimum_order and quantity <= capacity and lead_days <= latest_day


def build_supplier_options(
    state: BusinessState,
    sku_id: str,
    required_units: int,
    original_supplier_id: str,
    delay_days: int,
    planning_horizon: date,
) -> list[SupplierOption]:
    if required_units <= 0:
        return []

    options = []
    supplier_names = {row["supplier_id"]: row.get("supplier_name", "") for row in state.suppliers}
    offers = sorted(
        (row for row in state.supplier_offers if row["sku_id"] == sku_id),
        key=lambda row: row["supplier_id"],
    )
    for offer in offers:
        quantity = max(required_units, offer["min_order_units"])
        lead_days = offer["lead_time_days"] + (delay_days if offer["supplier_id"] == original_supplier_id else 0)
        arrival = state.as_of.date() + timedelta(days=lead_days)
        reasons = []
        if quantity > offer["capacity_units"]:
            reasons.append("capacity_exceeded")
        if arrival > planning_horizon:
            reasons.append("arrival_after_planning_horizon")
        options.append(
            SupplierOption(
                supplier_id=offer["supplier_id"],
                supplier_name=supplier_names.get(offer["supplier_id"], ""),
                sku_id=sku_id,
                quantity_units=quantity,
                unit_cost_rupees=offer["unit_cost_rupees"],
                total_cost_rupees=quantity * offer["unit_cost_rupees"],
                lead_time_days=lead_days,
                scenario_arrival_date=arrival,
                min_order_units=offer["min_order_units"],
                capacity_units=offer["capacity_units"],
                feasible=not reasons,
                reasons=reasons,
            )
        )
    return options
