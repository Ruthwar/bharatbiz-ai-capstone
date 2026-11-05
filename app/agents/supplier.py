def supplier_is_feasible(quantity: int, minimum_order: int, capacity: int, lead_days: int, latest_day: int) -> bool:
    return quantity >= minimum_order and quantity <= capacity and lead_days <= latest_day
