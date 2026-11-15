import csv
import os
import re
from datetime import datetime, timedelta
from pathlib import Path

from app.agents.orders import allocate_by_priority
from app.schemas.contracts import BusinessState
from app.state import DEFAULT_DATA_DIR

RECURRING_WINDOW_DAYS = 30
URGENT = re.compile(r"\b(?:urgent(?:ly)?|immediately|asap|running out|no stock|out of stock)\b", re.I)
COMPLAINTS = ("delivery_complaint", "damaged_item", "missing_item")


def order_history(retailer_id: str, data_dir: Path | None = None) -> dict:
    base = data_dir or Path(os.getenv("DATA_DIR", str(DEFAULT_DATA_DIR)))
    path = base / "historical_order_lines.csv"
    if not path.exists():
        return {"available": False, "lines": 0}
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = [row for row in csv.DictReader(handle) if row["retailer_id"] == retailer_id]
    return {
        "available": True,
        "lines": len(rows),
        "orders": len({row["order_id"] for row in rows}),
        "last_order_date": max((row["order_date"] for row in rows), default=None),
        "skus": sorted({row["sku_id"] for row in rows}),
    }


def follow_up_priority(
    state: BusinessState,
    retailer_id: str,
    intent: str,
    text: str,
    sku_id: str | None,
    prior_same_issue: int,
) -> tuple[str, list[str]]:
    record = next((row for row in state.retailers if row["retailer_id"] == retailer_id), {})
    allocations = [row for row in allocate_by_priority(state) if row.retailer_id == retailer_id]
    reasons = []
    if intent in COMPLAINTS and prior_same_issue:
        reasons.append(
            f"recurring: {intent.replace('_', ' ')} reported {prior_same_issue + 1} times in {RECURRING_WINDOW_DAYS} days"
        )
    if record.get("service_priority") == "high":
        reasons.append("retailer has high service priority")
    if any(row.priority == "high" and row.sku_id == sku_id for row in allocations):
        reasons.append("retailer has a high-priority open order for this product")
    urgent = URGENT.search(text)
    if urgent:
        reasons.append(f"message says '{urgent.group(0)}'")
    return ("high" if reasons else "normal"), reasons


def retailer_overview(
    state: BusinessState,
    retailer_id: str,
    store,
    now: datetime,
    data_dir: Path | None = None,
) -> dict:
    record = next((row for row in state.retailers if row["retailer_id"] == retailer_id), None)
    if record is None:
        raise LookupError(f"retailer {retailer_id} not found")
    since = (now - timedelta(days=RECURRING_WINDOW_DAYS)).isoformat()
    recent = store.interactions_for(retailer_id, since)
    counts = {}
    for row in recent:
        counts[row["intent"]] = counts.get(row["intent"], 0) + 1
    return {
        "retailer": record,
        "history": order_history(retailer_id, data_dir),
        "open_orders": [
            row.model_dump(mode="json")
            for row in allocate_by_priority(state)
            if row.retailer_id == retailer_id
        ],
        "cases": store.list_cases(retailer_id=retailer_id),
        "interactions_30d": counts,
        "recurring_issues": [
            {"intent": intent, "count": count}
            for intent, count in sorted(counts.items())
            if intent in COMPLAINTS and count >= 2
        ],
    }
