def allocate_fifo(orders: list[dict], available_by_sku: dict[str, int]) -> list[dict]:
    """Transparent FIFO baseline. Replace/compare with an agreed OR-Tools model."""
    remaining = dict(available_by_sku)
    results = []
    for order in sorted(orders, key=lambda row: (row["order_date"], row["order_id"])):
        sku = order["sku_id"]
        fulfilled = min(order["quantity_units"], remaining.get(sku, 0))
        remaining[sku] = remaining.get(sku, 0) - fulfilled
        results.append({"order_id": order["order_id"], "fulfilled_units": fulfilled,
                        "unmet_units": order["quantity_units"] - fulfilled})
    return results
