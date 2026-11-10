import csv
import json
import os
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from app.schemas.contracts import BusinessState

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = PROJECT_ROOT / "data" / "synthetic"


class StateLoadError(ValueError):
    pass


class StateVersionMismatch(StateLoadError):
    pass


def _read_csv(path: Path, integer_fields: set[str], decimal_fields: set[str] | None = None) -> list[dict]:
    if not path.exists():
        raise StateLoadError(f"Missing synthetic state file: {path}")
    decimal_fields = decimal_fields or set()
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    try:
        return [
            {
                key: (
                    int(value) if key in integer_fields
                    else Decimal(value) if key in decimal_fields
                    else value
                )
                for key, value in row.items()
            }
            for row in rows
        ]
    except (TypeError, ValueError, InvalidOperation) as exc:
        raise StateLoadError(f"Invalid numeric value in {path}") from exc


def _require_unique(rows: list[dict], field: str, source: str) -> None:
    values = [row[field] for row in rows]
    if len(values) != len(set(values)):
        raise StateLoadError(f"Duplicate {field} in {source}")


def load_business_state(data_dir: Path | None = None, expected_version: str | None = None) -> BusinessState:
    base = data_dir or Path(os.getenv("DATA_DIR", str(DEFAULT_DATA_DIR)))
    state_path = base / "business_state.json"
    if not state_path.exists():
        raise StateLoadError(f"Missing synthetic state file: {state_path}")
    try:
        raw = json.loads(state_path.read_text(encoding="utf-8"))
        as_of = datetime.fromisoformat(f"{raw['as_of_date']}T00:00:00+05:30")
        cash_balance = Decimal(str(raw["opening_cash_rupees"]))
        minimum_buffer = Decimal(str(raw["minimum_cash_buffer_rupees"]))
    except (KeyError, TypeError, ValueError, InvalidOperation, json.JSONDecodeError) as exc:
        raise StateLoadError(f"Invalid business state: {state_path}") from exc

    if expected_version is not None and raw["state_version"] != expected_version:
        raise StateVersionMismatch(
            f"Requested state {expected_version} does not match loaded state {raw['state_version']}"
        )

    products = _read_csv(
        base / "products.csv",
        {"units_per_case"},
        {"unit_cost_rupees"},
    )
    inventory = _read_csv(
        base / "inventory.csv",
        {"on_hand_units", "reserved_units", "incoming_units", "reorder_point_units"},
    )
    open_orders = _read_csv(base / "open_orders.csv", {"quantity_units"})
    suppliers = _read_csv(base / "suppliers.csv", {"lead_time_days", "payment_terms_days"})
    retailers = _read_csv(base / "retailers.csv", set())
    supplier_offers = _read_csv(
        base / "supplier_products.csv",
        {"min_order_units", "capacity_units", "lead_time_days"},
        {"unit_cost_rupees"},
    )

    _require_unique(products, "sku_id", "products.csv")
    _require_unique(inventory, "sku_id", "inventory.csv")
    _require_unique(open_orders, "order_id", "open_orders.csv")
    _require_unique(suppliers, "supplier_id", "suppliers.csv")
    _require_unique(retailers, "retailer_id", "retailers.csv")

    return BusinessState(
        state_version=raw["state_version"],
        as_of=as_of,
        products=products,
        inventory=inventory,
        open_orders=open_orders,
        suppliers=suppliers,
        retailers=retailers,
        supplier_offers=supplier_offers,
        cash_balance_rupees=cash_balance,
        minimum_cash_buffer_rupees=minimum_buffer,
    )
