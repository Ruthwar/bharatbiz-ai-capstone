def verify_cash(ending_cash_paise: int, minimum_buffer_paise: int) -> list[str]:
    return [] if ending_cash_paise >= minimum_buffer_paise else ["minimum_cash_buffer_breached"]


def verify_allocations(rows: list[dict], stock_by_sku: dict[str, int]) -> list[str]:
    totals: dict[str, int] = {}
    for row in rows:
        totals[row["sku_id"]] = totals.get(row["sku_id"], 0) + row["fulfilled_units"]
    return [f"stock_exceeded:{sku}" for sku, total in totals.items() if total > stock_by_sku.get(sku, 0)]
