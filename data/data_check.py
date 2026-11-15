"""Validate the committed synthetic pack and print its inventory."""

import csv
import json
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SYNTHETIC = ROOT / "data" / "synthetic"
EVAL = ROOT / "data" / "eval"

EXPECTED_COUNTS = {
    "products": 12,
    "suppliers": 5,
    "retailers": 20,
    "supplier_products": 47,
    "inventory": 12,
    "historical_order_lines": 80,
    "open_orders": 30,
    "supplier_deliveries": 50,
    "scheduled_receivables": 30,
    "retailer_complaints": 25,
    "market_observations": 30,
    "cash_ledger": 30,
    "scenarios": 8,
}
PRIMARY_KEYS = {
    "products": "sku_id",
    "suppliers": "supplier_id",
    "retailers": "retailer_id",
    "inventory": "sku_id",
    "historical_order_lines": "order_id",
    "open_orders": "order_id",
    "supplier_deliveries": "delivery_id",
    "scheduled_receivables": "receivable_id",
    "retailer_complaints": "complaint_id",
    "market_observations": "observation_id",
    "cash_ledger": "entry_id",
    "scenarios": "scenario_id",
}


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _read_csv(name):
    with (SYNTHETIC / f"{name}.csv").open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _read_jsonl(name):
    with (SYNTHETIC / f"{name}.jsonl").open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _read_eval_jsonl(name):
    with (EVAL / name).open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _require_money(value, label):
    try:
        parsed = Decimal(value)
    except (InvalidOperation, TypeError):
        raise ValueError(f"{label}: invalid money value {value!r}")
    _require(parsed == parsed.quantize(Decimal("0.01")), f"{label}: money must have two decimals")


def _require_state(row, state_version, label):
    _require(row.get("state_version") == state_version, f"{label}: state_version mismatch")


def validate():
    tables = {name: _read_csv(name) for name in EXPECTED_COUNTS}
    for name, expected in EXPECTED_COUNTS.items():
        _require(len(tables[name]) == expected, f"{name}: expected {expected} rows, found {len(tables[name])}")

    for name, key in PRIMARY_KEYS.items():
        values = [row[key] for row in tables[name]]
        _require(len(values) == len(set(values)), f"{name}: duplicate {key}")

    for name in EXPECTED_COUNTS.keys() - {"scenarios"}:
        _require(all(row.get("source_type") == "synthetic" for row in tables[name]), f"{name}: invalid source_type")
    _require(all(row["verified_business"] == "false" for row in tables["retailers"]), "retailers: unexpected verified business")

    products = {row["sku_id"] for row in tables["products"]}
    suppliers = {row["supplier_id"] for row in tables["suppliers"]}
    retailers = {row["retailer_id"] for row in tables["retailers"]}
    _require({row["sku_id"] for row in tables["inventory"]} == products, "inventory: SKU coverage differs from products")

    offers = {(row["supplier_id"], row["sku_id"]) for row in tables["supplier_products"]}
    _require(len(offers) == len(tables["supplier_products"]), "supplier_products: duplicate supplier-SKU pair")
    _require(all(supplier in suppliers and sku in products for supplier, sku in offers), "supplier_products: unresolved reference")

    for name in ("historical_order_lines", "open_orders"):
        for row in tables[name]:
            _require(row["retailer_id"] in retailers, f"{name}: unresolved {row['retailer_id']}")
            _require(row["sku_id"] in products, f"{name}: unresolved {row['sku_id']}")
    for row in tables["supplier_deliveries"]:
        pair = (row["supplier_id"], row["sku_id"])
        _require(pair in offers, f"supplier_deliveries: unapproved supplier-SKU pair {pair}")
        _require(date.fromisoformat(row["actual_date"]) >= date.fromisoformat(row["planned_date"]), f"{row['delivery_id']}: negative delivery delay")
        _require(row["unit"] == next(item["base_unit"] for item in tables["products"] if item["sku_id"] == row["sku_id"]), f"{row['delivery_id']}: unit mismatch")

    state = json.loads((SYNTHETIC / "business_state.json").read_text(encoding="utf-8"))
    state_version = state["state_version"]
    for name in ("scheduled_receivables", "retailer_complaints", "market_observations"):
        for row in tables[name]:
            _require_state(row, state_version, name)
    for row in tables["scheduled_receivables"]:
        _require(row["retailer_id"] in retailers, f"scheduled_receivables: unresolved {row['retailer_id']}")
        _require(row["currency"] == "INR", f"{row['receivable_id']}: unsupported currency")
        _require_money(row["amount_rupees"], f"{row['receivable_id']}: amount_rupees")
        _require(date.fromisoformat(row["due_date"]) >= date.fromisoformat(row["issue_date"]), f"{row['receivable_id']}: due date before issue date")
    for row in tables["retailer_complaints"]:
        _require(row["retailer_id"] in retailers, f"retailer_complaints: unresolved {row['retailer_id']}")
        _require(row["sku_id"] in products, f"retailer_complaints: unresolved {row['sku_id']}")
        date.fromisoformat(row["complaint_date"])
    for row in tables["market_observations"]:
        _require(row["retailer_id"] in retailers, f"market_observations: unresolved {row['retailer_id']}")
        _require(row["sku_id"] in products, f"market_observations: unresolved {row['sku_id']}")
        date.fromisoformat(row["observed_date"])

    messages = _read_jsonl("messages")
    events = _read_jsonl("events")
    _require(len(messages) == len(events) == 1000, "messages/events: expected 1,000 records each")
    message_ids = {message["message_id"] for message in messages}
    event_ids = [event["event_id"] for event in events]
    _require(len(message_ids) == len(messages), "messages: duplicate message_id")
    _require(len(event_ids) == len(set(event_ids)), "events: duplicate event_id")
    source_ids = [source for event in events for source in event["source_message_ids"]]
    _require(len(source_ids) == len(set(source_ids)) == 1000, "events: source messages are not one-to-one")
    _require(set(source_ids) == message_ids, "events: unresolved or missing message reference")
    for message in messages:
        _require(message["consent_status"] == "synthetic", f"{message['message_id']}: invalid consent status")
        _require(message["observed_at"].endswith("+05:30"), f"{message['message_id']}: timestamp is not IST")
        _require(isinstance(json.loads(message["entities"]), dict), f"{message['message_id']}: invalid entities")

    held_out = _read_eval_jsonl("heldout_extraction.jsonl")
    held_out_ids = [row["message_id"] for row in held_out]
    _require(len(held_out_ids) == len(set(held_out_ids)), "held-out: duplicate message_id")
    _require(not set(held_out_ids) & message_ids, "held-out: overlaps training message IDs")
    allowed_intents = {"delivery_complaint", "damaged_item", "missing_item", "product_request", "scheme_question", "supplier_delay", "competitor_observation", "other"}
    for row in held_out:
        _require(row["split"] == "held_out", f"{row['message_id']}: invalid split")
        _require(row["source_type"] == "synthetic", f"{row['message_id']}: invalid source_type")
        _require(row["state_version"] == state_version, f"{row['message_id']}: state_version mismatch")
        _require(row["intent"] in allowed_intents, f"{row['message_id']}: invalid intent")
        _require(all(span in row["text"] for span in row["evidence_spans"]), f"{row['message_id']}: evidence span not found")
        _require(isinstance(row["entities"], dict), f"{row['message_id']}: invalid entities")

    scenarios_json = json.loads((SYNTHETIC / "scenarios.json").read_text(encoding="utf-8"))
    _require(scenarios_json == tables["scenarios"], "scenarios: CSV and JSON definitions differ")
    fixture = json.loads((SYNTHETIC / "scenario_fixtures" / "SCN-003.json").read_text(encoding="utf-8"))
    _require(fixture["scenario_id"] == "SCN-003", "SCN-003 fixture: wrong scenario id")
    _require(fixture["message"]["state_version"] == state_version, "SCN-003 fixture: state_version mismatch")
    _require(fixture["message"]["source_type"] == "supplier_update", "SCN-003 fixture: wrong source type")
    _require(fixture["message"]["sender"]["party_id"] == fixture["assumptions"]["original_supplier_id"], "SCN-003 fixture: sender/supplier mismatch")
    _require(fixture["assumptions"]["sku_id"] == "SKU-003", "SCN-003 fixture: unexpected SKU")


def main():
    for path in sorted(SYNTHETIC.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(ROOT)
        if path.suffix == ".csv":
            with path.open(encoding="utf-8", newline="") as handle:
                reader = csv.DictReader(handle)
                rows = list(reader)
            print(f"{relative} | rows={len(rows)} | cols={reader.fieldnames}")
        else:
            print(f"{relative} (non-CSV)")
    validate()
    print("Synthetic data quality checks passed.")


if __name__ == "__main__":
    main()
