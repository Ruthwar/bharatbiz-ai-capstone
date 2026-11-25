"""Load the synthetic policy-review tables used by advisory scenarios."""

import csv
import os
from pathlib import Path

from app.state import DEFAULT_DATA_DIR

TABLE_FILES = {
    "credit_limits": "retailer_credit_limits.csv",
    "receivables": "scheduled_receivables.csv",
    "schemes": "trade_schemes.csv",
    "delivery_evidence": "delivery_evidence.csv",
    "batches": "batch_lots.csv",
    "recalls": "recall_notices.csv",
    "routes": "dispatch_routes.csv",
    "dispatch_orders": "dispatch_orders.csv",
}


def load_advisory_tables(data_dir: Path | None = None) -> dict[str, list[dict]]:
    base = Path(data_dir) if data_dir else Path(os.getenv("DATA_DIR", str(DEFAULT_DATA_DIR)))
    tables: dict[str, list[dict]] = {}
    for name, filename in TABLE_FILES.items():
        path = base / filename
        with path.open(newline="", encoding="utf-8-sig") as handle:
            tables[name] = list(csv.DictReader(handle))
    return tables
