"""Generate deterministic, clearly synthetic capstone data aligned to the master plan."""
from __future__ import annotations

import argparse
import csv
import json
import random
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

PRODUCTS = [
    ("Rice", "5 kg bag", "kg", 500), ("Rice", "10 kg bag", "kg", 1000),
    ("Cooking oil", "1 L pouch", "litre", 100), ("Cooking oil", "5 L tin", "litre", 500),
    ("Biscuits", "family carton", "pieces", 240), ("Biscuits", "small carton", "pieces", 120),
    ("Soap", "case", "pieces", 144), ("Shampoo", "sachet carton", "pieces", 500),
    ("Tea", "1 kg pack", "kg", 100), ("Beverage", "crate", "pieces", 24),
    ("Detergent", "case", "kg", 120), ("Toothpaste", "case", "pieces", 96),
]
INTENTS = ["delivery_complaint", "damaged_item", "missing_item", "product_request", "scheme_question", "supplier_delay", "competitor_observation", "other"]
TEMPLATES = {
    "delivery_complaint": ["Delivery for {product} arrived late at shop {retailer}.", "We are still waiting for the {product} order; please check delivery."],
    "damaged_item": ["Some {product} cartons arrived damaged at {retailer}.", "Please note damaged {product} in the last delivery."],
    "missing_item": ["The {product} quantity was short in today's delivery.", "{retailer} reports {product} missing from the order."],
    "product_request": ["Customers at {retailer} are asking for a smaller {product} pack.", "Please check availability of {product} for next visit."],
    "scheme_question": ["Does the current scheme apply to {product}?", "Please confirm the offer details for {product}."],
    "supplier_delay": ["Supplier {supplier} reports a delay for {product}; revised date is not confirmed.", "{supplier} can dispatch part of the {product} quantity tomorrow; balance timing is unknown."],
    "competitor_observation": ["Sales visit report: nearby competitor promotion on {product}; not verified.", "A shop reported a competitor offer for {product}; source needs corroboration."],
    "other": ["Please follow up with {retailer} during the next visit.", "General update about {product}; no quantity or date stated."],
}


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def generate(out: Path, seed: int) -> None:
    rng = random.Random(seed)
    out.mkdir(parents=True, exist_ok=True)
    base = date(2026, 11, 1)
    products = [{"sku_id": f"SKU-{i+1:03}", "category": cat, "product_name": cat,
                 "pack_description": pack, "base_unit": unit, "units_per_case": units,
                 "unit_cost_rupees": format(Decimal(80) + Decimal(i) * Decimal("9.25"), ".2f"),
                 "source_type": "synthetic"}
                for i, (cat, pack, unit, units) in enumerate(PRODUCTS)]
    suppliers = [{"supplier_id": f"SUP-{i+1:03}", "supplier_name": f"Synthetic Supplier {i+1}",
                  "lead_time_days": 1 + (i % 4), "payment_terms_days": [0, 7, 14][i % 3],
                  "source_type": "synthetic"} for i in range(5)]
    retailers = [{"retailer_id": f"RET-{i+1:03}", "area": f"Area-{i % 4 + 1}",
                  "service_priority": ["normal", "normal", "high"][i % 3],
                  "source_type": "synthetic", "verified_business": "false"} for i in range(20)]
    offers = []
    for s in suppliers:
        for p in products:
            if rng.random() < .72:
                unit_cost = Decimal(p["unit_cost_rupees"]) + Decimal(rng.randint(-500, 1000)) / 100
                offers.append({"supplier_id": s["supplier_id"], "sku_id": p["sku_id"],
                               "unit_cost_rupees": format(unit_cost, ".2f"),
                               "min_order_units": rng.choice([1, 5, 10]), "capacity_units": rng.randint(40, 180),
                               "lead_time_days": s["lead_time_days"], "source_type": "synthetic"})
    inventory = [{"sku_id": p["sku_id"], "on_hand_units": rng.randint(30, 150),
                  "reserved_units": rng.randint(0, 12), "incoming_units": rng.randint(0, 30),
                  "reorder_point_units": 35, "unit": p["base_unit"], "as_of_date": base.isoformat(),
                  "source_type": "synthetic"} for p in products]
    orders = []
    for i in range(80):
        p, r = rng.choice(products), rng.choice(retailers)
        d = base - timedelta(days=rng.randint(1, 60))
        orders.append({"order_id": f"HIS-{i+1:04}", "retailer_id": r["retailer_id"], "sku_id": p["sku_id"],
                       "order_date": d.isoformat(), "quantity_units": rng.randint(2, 24), "unit": p["base_unit"],
                       "status": "delivered", "source_type": "synthetic"})
    open_orders = []
    for i in range(30):
        p, r = rng.choice(products), rng.choice(retailers)
        d = base + timedelta(days=rng.randint(0, 3))
        open_orders.append({"order_id": f"ORD-{i+1:04}", "retailer_id": r["retailer_id"], "sku_id": p["sku_id"],
                            "order_date": base.isoformat(), "requested_delivery_date": d.isoformat(),
                            "quantity_units": rng.randint(3, 28), "unit": p["base_unit"], "priority": r["service_priority"],
                            "status": "open", "source_type": "synthetic"})
    deliveries = []
    for i in range(50):
        s, p = rng.choice(suppliers), rng.choice(products)
        delay = rng.choice([0, 0, 0, 1, 2])
        planned = base - timedelta(days=rng.randint(1, 30))
        deliveries.append({"delivery_id": f"DEL-{i+1:04}", "purchase_order_id": f"PO-{i+1:04}",
                           "supplier_id": s["supplier_id"], "sku_id": p["sku_id"],
                           "quantity_units": rng.randint(5, 50), "planned_date": planned.isoformat(),
                           "actual_date": (planned + timedelta(days=delay)).isoformat(), "delay_days": delay,
                           "status": "delivered", "source_type": "synthetic"})
    cash = [{"entry_id": f"CASH-{i+1:03}", "entry_date": (base - timedelta(days=29-i)).isoformat(),
             "entry_type": "inflow" if i % 3 == 0 else "outflow",
             "amount_rupees": format(
                 Decimal(25000) if i % 3 == 0 else -Decimal(rng.randint(300000, 1000000)) / 100,
                 ".2f",
             ),
             "minimum_buffer_rupees": "50000.00", "source_type": "synthetic"} for i in range(30)]
    scenarios = [
        {"scenario_id":"SCN-001","name":"Baseline day","trigger":"Use starting operational state","expected":"Feasible plan or explicit infeasibility; enforce stock, supplier and cash constraints"},
        {"scenario_id":"SCN-002","name":"Biscuit demand spike","trigger":"Increase biscuit demand by 60 percent for two simulated days","expected":"Recompute stock and orders; show unmet demand and replan"},
        {"scenario_id":"SCN-003","name":"Supplier delay","trigger":"Delay one supplier by two days; balance date unknown","expected":"Compare alternatives; do not invent a revised date"},
        {"scenario_id":"SCN-004","name":"Liquidity stress","trigger":"Delay a ₹30,000.00 retailer payment by seven days","expected":"Protect the ₹50,000.00 minimum buffer or report infeasible"},
        {"scenario_id":"SCN-005","name":"Inventory discrepancy","trigger":"Physical count finds 15 fewer base units for one SKU","expected":"Reallocate without negative stock"},
        {"scenario_id":"SCN-006","name":"Retailer complaint","trigger":"Late delivery complaint with product mention but no order ID","expected":"Preserve exact evidence and request clarification for unmatched order"},
        {"scenario_id":"SCN-007","name":"Competitor report","trigger":"One uncorroborated promotion observation","expected":"Show as reported/unverified, not as established market fact"},
        {"scenario_id":"SCN-008","name":"Combined disruption","trigger":"Demand increase, supplier delay and delayed payment together","expected":"Replan under hard constraints or explain infeasibility"},
    ]
    write_csv(out / "products.csv", products)
    write_csv(out / "suppliers.csv", suppliers)
    write_csv(out / "retailers.csv", retailers)
    write_csv(out / "supplier_products.csv", offers)
    write_csv(out / "inventory.csv", inventory)
    write_csv(out / "historical_order_lines.csv", orders)
    write_csv(out / "open_orders.csv", open_orders)
    write_csv(out / "supplier_deliveries.csv", deliveries)
    write_csv(out / "cash_ledger.csv", cash)
    (out / "business_state.json").write_text(json.dumps({
        "state_version": "synthetic-v2-seed-" + str(seed),
        "as_of_date": base.isoformat(),
        "opening_cash_rupees": "250000.00",
        "minimum_cash_buffer_rupees": "50000.00",
        "source_type": "synthetic",
        "note": "Fictional simulation state; currency is exact decimal rupees."
    }, indent=2), encoding="utf-8")
    write_csv(out / "scenarios.csv", scenarios)
    (out / "scenarios.json").write_text(json.dumps(scenarios, indent=2), encoding="utf-8")
    messages, events = [], []
    for i in range(1000):
        intent = INTENTS[i % len(INTENTS)]
        product, retailer, supplier = rng.choice(products), rng.choice(retailers), rng.choice(suppliers)
        template = rng.choice(TEMPLATES[intent])
        text = template.format(product=product["product_name"], retailer=retailer["retailer_id"], supplier=supplier["supplier_id"])
        evidence = next((word for word in ("late", "damaged", "short", "asking", "scheme", "delay", "not verified", "no quantity") if word in text.lower()), "")
        messages.append({"message_id": f"MSG-{i+1:05}", "source_type": "synthetic" if intent not in ("supplier_delay",) else "supplier_update",
                         "observed_at": f"2026-10-{(i % 28)+1:02}T10:00:00+05:30", "language": "English",
                         "text": text, "intent": intent, "entities": json.dumps({"product": product["product_name"], "retailer_id": retailer["retailer_id"] if intent != "supplier_delay" else None,
                                                                                     "supplier_id": supplier["supplier_id"] if intent == "supplier_delay" else None}),
                         "urgency": "unclear" if i % 5 == 0 else "normal", "evidence_span": evidence,
                         "uncertainty": "Synthetic example; exact order/date/quantity may be unstated.", "review_label": "correct",
                         "consent_status": "synthetic", "source_type_label": "synthetic"})
        events.append({"event_id": f"EVT-{i+1:05}", "source_message_ids": [f"MSG-{i+1:05}"],
                       "event_type": intent, "extracted_facts": [], "inferences": {},
                       "evidence_spans": [text],
                       "uncertainties": ["Synthetic annotation; order/date/quantity are not asserted unless stated in the source."],
                       "human_review_required": True, "status": "pending_review",
                       "state_version": "synthetic-v2-seed-" + str(seed)})
    with (out / "messages.jsonl").open("w", encoding="utf-8") as f:
        for row in messages:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    with (out / "events.jsonl").open("w", encoding="utf-8") as f:
        for row in events:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    docs = out.parent / "knowledge_docs"
    docs.mkdir(parents=True, exist_ok=True)
    for i, (title, body) in enumerate([
        ("Synthetic delay handling guide", "SIMULATION ONLY. If supplier arrival is delayed, verify affected orders and stock. Do not promise a date not confirmed by the supplier. A manager reviews proposed alternatives."),
        ("Synthetic retailer complaint procedure", "SIMULATION ONLY. Record original complaint, source, timestamp and evidence. Link an order only with a reliable reference. Keep follow-up pending until a human confirms the outcome."),
        ("Synthetic competitor observation note", "SIMULATION ONLY. Competitor reports are observations, not verified market facts. Preserve source and date; seek independent corroboration before making a decision."),
        ("Synthetic cash buffer policy", "SIMULATION ONLY. Candidate plans must preserve the configured minimum cash buffer. If the data is incomplete or no feasible plan exists, report the limitation for manager review."),
    ], 1):
        (docs / f"SYN-DOC-{i:03}.txt").write_text(f"{title}\nSource: synthetic demonstration policy\nEffective date: 2026-11-01\n\n{body}\n", encoding="utf-8")
    (out / "DATA_DICTIONARY.md").write_text(
        "# Synthetic dataset dictionary\n\nGenerated by `scripts/generate_synthetic_data.py`; all entities and events are fictional. Reproducible with a fixed seed. Currency is exact decimal rupees with two decimal places; quantities use the explicit `unit`/`base_unit` field. Dates are ISO 8601; timestamps include +05:30. `messages.jsonl` contains 1,000 labelled synthetic examples; `events.jsonl` has corresponding evidence-linked event annotations. Keep both separate from any permissioned pilot data. `scenarios.csv/json` provide eight repeatable cases. Supplier offers are valid only for listed supplier-SKU rows. No value represents verified local prices or business activity.\n\nTables: products, suppliers, retailers, supplier_products, inventory, historical_order_lines, open_orders, supplier_deliveries, cash_ledger, scenarios and messages/events. Stable IDs connect related rows. Unknown source facts must remain unknown.\n",
        encoding="utf-8")
    print(f"Generated synthetic pack at {out} (seed={seed}, messages={len(messages)}, scenarios={len(scenarios)})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=20261105)
    parser.add_argument("--out", type=Path, default=Path("data/synthetic"))
    args = parser.parse_args()
    generate(args.out, args.seed)
