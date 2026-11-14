"""Validate the committed synthetic pack and print its inventory."""

import csv
import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SYNTHETIC = ROOT / "data" / "synthetic"

EXPECTED_COUNTS = {
    "products": 12,
    "suppliers": 5,
    "retailers": 20,
    "supplier_products": 47,
    "inventory": 12,
    "historical_order_lines": 80,
    "open_orders": 30,
    "supplier_deliveries": 50,
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

    scenarios_json = json.loads((SYNTHETIC / "scenarios.json").read_text(encoding="utf-8"))
    _require(scenarios_json == tables["scenarios"], "scenarios: CSV and JSON definitions differ")


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
