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
SUPPLIERS = [
    ("Shree Ganesh Trading Co", 1, 0),
    ("Balaji Wholesale Distributors", 2, 7),
    ("Krishna Rice Mills", 3, 14),
    ("Anand Oil Agencies", 4, 0),
    ("Sri Venkateswara FMCG Supply", 1, 7),
]
LOCALITIES = ["Kukatpally", "Ameerpet", "Dilsukhnagar", "Secunderabad"]
RETAILERS = [
    ("Sri Sai Kirana Store", "kirana"),
    ("New Balaji General Store", "general_store"),
    ("Lakshmi Provision Store", "provision_store"),
    ("Ganesh Supermarket", "supermarket"),
    ("Sai Ram Mini Market", "mini_market"),
    ("Maa Bhagya Kirana", "kirana"),
    ("Sri Krishna Stores", "general_store"),
    ("Anjaneya General Stores", "general_store"),
    ("Padmavathi Kirana", "kirana"),
    ("Royal Mart Express", "convenience_store"),
    ("New Sai Kirana", "kirana"),
    ("Bhagyalakshmi Stores", "provision_store"),
    ("Sri Laxmi Traders", "wholesale_retail"),
    ("Om Sai Provision Store", "provision_store"),
    ("Venkateswara Kirana", "kirana"),
    ("Sneha General Store", "general_store"),
    ("Sri Vinayaka Stores", "general_store"),
    ("Mahalakshmi Mini Mart", "mini_market"),
    ("Sai Datta Kirana", "kirana"),
    ("New Krishna Provision", "provision_store"),
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


def generate_historical_deliveries(num_rows: int, suppliers: list[dict], products: list[dict],
                                   offers: list[dict], rng: random.Random, base: date,
                                   state_version: str) -> list[dict]:
    """Generate deterministic delivery history using valid supplier/SKU offer pairs."""
    deliveries = []
    offer_by_pair = {(offer["supplier_id"], offer["sku_id"]): offer for offer in offers}
    offers_by_supplier = {}
    for offer in offers:
        offers_by_supplier.setdefault(offer["supplier_id"], []).append(offer)
    for i in range(1, num_rows + 1):
        supplier, product = rng.choice(suppliers), rng.choice(products)
        offer = offer_by_pair.get((supplier["supplier_id"], product["sku_id"]))
        if offer is None:
            supplier_offers = offers_by_supplier[supplier["supplier_id"]]
            offer = supplier_offers[(i - 1) % len(supplier_offers)]
        delay = rng.choice([0, 0, 0, 1, 2])
        planned = base - timedelta(days=rng.randint(1, 30))
        deliveries.append({
            "delivery_id": f"DEL-{i:04d}",
            "purchase_order_id": f"PO-{i:04d}",
            "supplier_id": offer["supplier_id"],
            "sku_id": offer["sku_id"],
            "quantity_units": rng.randint(5, 50),
            "planned_date": planned.isoformat(),
            "actual_date": (planned + timedelta(days=delay)).isoformat(),
            "delay_days": delay,
            "status": "delivered",
            "unit": product["base_unit"] if product["sku_id"] == offer["sku_id"] else next(p["base_unit"] for p in products if p["sku_id"] == offer["sku_id"]),
            "state_version": state_version,
            "source_type": "synthetic",
        })
    return deliveries


def generate_scheduled_receivables(num_rows: int, retailers: list[dict], rng: random.Random,
                                   base: date, state_version: str) -> list[dict]:
    """Generate deterministic scheduled retailer receivables."""
    receivables = []
    for i in range(1, num_rows + 1):
        issue_date = base - timedelta(days=rng.randint(1, 30))
        due_date = issue_date + timedelta(days=rng.choice([7, 14, 15, 21]))

        days_until_due = (due_date - base).days

        if days_until_due < 0:
            status = "overdue"
        elif days_until_due <= 7:
            status = "due_soon"
        else:
            status = "scheduled"
        receivables.append({
            "receivable_id": f"REC-{i:04d}",
            "retailer_id": rng.choice(retailers)["retailer_id"],
            "amount_rupees": format(Decimal(rng.randint(500000, 7500000)) / 100, ".2f"),
            "currency": "INR",
            "issue_date": issue_date.isoformat(),
            "due_date": due_date.isoformat(),
            "status": status,
            "state_version": state_version,
            "source_type": "synthetic",
        })
    return receivables

def generate_retailer_complaints(num_rows: int, retailers: list[dict], products: list[dict], rng: random.Random,
                                 base_date: date, state_version: str) -> list[dict]:
    """Generates historical and active retailer complaint records."""
    complaints = []
    categories = ["delivery_delay", "damaged_goods", "short_shipment", "billing_dispute"]
    statuses = ["open", "investigating", "resolved", "closed"]
    for i in range(1, num_rows + 1):
        r = rng.choice(retailers)
        p = rng.choice(products)
        logged_date = base_date - timedelta(days=rng.randint(1, 45))
        status = rng.choice(statuses)
        if status in {"open", "investigating"}:
            resolution_notes = "Pending review"
        else:
            resolution_notes = rng.choice([
                "Resolved via credit note",
                "Resolved after replacement shipment",
                "Closed after retailer confirmation",
            ])
        complaints.append({
            "complaint_id": f"CMP-{i:03d}",
            "retailer_id": r["retailer_id"],
            "sku_id": p["sku_id"],
            "complaint_date": logged_date.isoformat(),
            "category": rng.choice(categories),
            "status": status,
            "resolution_notes": resolution_notes,
            "state_version": state_version,
            "source_type": "synthetic"
        })
    return complaints


def generate_market_observations(num_rows: int, retailers: list[dict], products: list[dict],
                                 rng: random.Random, base: date, state_version: str) -> list[dict]:
    """Generate attributed, explicitly uncertain market observations."""
    signal_types = ["competitor_promotion", "local_event", "price_observation", "availability_report"]
    directions = ["up", "down", "unchanged", "unclear"]
    rows = []
    for i in range(1, num_rows + 1):
        retailer = rng.choice(retailers)
        product = rng.choice(products)
        observed = base - timedelta(days=rng.randint(1, 30))
        signal_type = rng.choice(signal_types)
        rows.append({
            "observation_id": f"MKT-{i:04d}",
            "source_id": f"VISIT-{i:04d}",
            "retailer_id": retailer["retailer_id"],
            "sku_id": product["sku_id"],
            "observed_date": observed.isoformat(),
            "signal_type": signal_type,
            "direction": rng.choice(directions),
            "observation_text": f"Synthetic {signal_type.replace('_', ' ')} observed near {retailer['retailer_name']}; corroboration required.",
            "corroboration_status": "single_source",
            "confidence": "low",
            "state_version": state_version,
            "source_type": "synthetic",
        })
    return rows
def generate_advisory_tables(out: Path, base: date, state_version: str,
                            retailers: list[dict], open_orders: list[dict]) -> None:
    """Policy-review tables for credit, schemes, delivery evidence, batches, recalls and dispatch."""
    credit = [
        {
            "retailer_id": row["retailer_id"],
            "credit_limit_rupees": format(Decimal(50000 + (index % 5) * 25000), ".2f"),
            "payment_terms_days": [0, 7, 14][index % 3],
            "status": "active",
            "reviewed_on": (base - timedelta(days=10)).isoformat(),
            "source_type": "synthetic",
        }
        for index, row in enumerate(retailers)
    ]
    schemes = [
        {"scheme_id": "SCM-001", "scheme_name": "Biscuit carton volume scheme", "sku_id": "SKU-005",
         "supplier_id": "SUP-001", "discount_percent": "5.00", "min_quantity_units": 20,
         "valid_from": (base - timedelta(days=15)).isoformat(), "valid_to": (base + timedelta(days=7)).isoformat(),
         "status": "approved", "source_type": "synthetic"},
        {"scheme_id": "SCM-002", "scheme_name": "Cooking oil litre scheme", "sku_id": "SKU-003",
         "supplier_id": "SUP-002", "discount_percent": "7.50", "min_quantity_units": 40,
         "valid_from": (base - timedelta(days=13)).isoformat(), "valid_to": (base + timedelta(days=1)).isoformat(),
         "status": "approved", "source_type": "synthetic"},
        {"scheme_id": "SCM-003", "scheme_name": "Rice bulk scheme", "sku_id": "SKU-001",
         "supplier_id": "SUP-003", "discount_percent": "10.00", "min_quantity_units": 100,
         "valid_from": (base - timedelta(days=45)).isoformat(), "valid_to": (base - timedelta(days=15)).isoformat(),
         "status": "approved", "source_type": "synthetic"},
        {"scheme_id": "SCM-004", "scheme_name": "Tea festive scheme", "sku_id": "SKU-009",
         "supplier_id": "SUP-005", "discount_percent": "12.00", "min_quantity_units": 10,
         "valid_from": (base - timedelta(days=3)).isoformat(), "valid_to": (base + timedelta(days=12)).isoformat(),
         "status": "approved", "source_type": "synthetic"},
    ]
    evidence = [
        {"evidence_id": "EVD-9001", "delivery_id": "DEL-9001", "purchase_order_id": "PO-9001",
         "retailer_id": "RET-004", "sku_id": "SKU-003", "ordered_units": 60, "received_units": 52,
         "damaged_units": 5, "wrong_item_units": 3, "unit": "litre", "invoice_reference": "INV-9001",
         "pod_reference": "POD-9001", "checked_on": (base - timedelta(days=1)).isoformat(),
         "status": "discrepancy_open", "source_type": "synthetic"},
        {"evidence_id": "EVD-9002", "delivery_id": "DEL-9002", "purchase_order_id": "PO-9002",
         "retailer_id": "RET-010", "sku_id": "SKU-005", "ordered_units": 48, "received_units": 48,
         "damaged_units": 0, "wrong_item_units": 0, "unit": "pieces", "invoice_reference": "INV-9002",
         "pod_reference": "POD-9002", "checked_on": (base - timedelta(days=3)).isoformat(),
         "status": "matched", "source_type": "synthetic"},
    ]
    batches = [
        {"batch_id": "BATCH-001", "sku_id": "SKU-009", "supplier_id": "SUP-005", "quantity_units": 120,
         "unit": "kg", "manufactured_on": "2026-09-01", "expiry_date": (base + timedelta(days=110)).isoformat(),
         "warehouse": "WH-01", "supplier_return_window_days": 30, "status": "released", "source_type": "synthetic"},
        {"batch_id": "BATCH-002", "sku_id": "SKU-009", "supplier_id": "SUP-005", "quantity_units": 80,
         "unit": "kg", "manufactured_on": "2026-10-01", "expiry_date": (base + timedelta(days=9)).isoformat(),
         "warehouse": "WH-01", "supplier_return_window_days": 14, "status": "released", "source_type": "synthetic"},
        {"batch_id": "BATCH-003", "sku_id": "SKU-003", "supplier_id": "SUP-002", "quantity_units": 140,
         "unit": "litre", "manufactured_on": "2026-08-15", "expiry_date": (base + timedelta(days=84)).isoformat(),
         "warehouse": "WH-02", "supplier_return_window_days": 14, "status": "released", "source_type": "synthetic"},
        {"batch_id": "BATCH-004", "sku_id": "SKU-005", "supplier_id": "SUP-001", "quantity_units": 300,
         "unit": "pieces", "manufactured_on": "2026-10-20", "expiry_date": (base + timedelta(days=150)).isoformat(),
         "warehouse": "WH-01", "supplier_return_window_days": 21, "status": "quality_hold", "source_type": "synthetic"},
        {"batch_id": "BATCH-005", "sku_id": "SKU-001", "supplier_id": "SUP-003", "quantity_units": 500,
         "unit": "kg", "manufactured_on": "2026-11-01", "expiry_date": (base + timedelta(days=160)).isoformat(),
         "warehouse": "WH-02", "supplier_return_window_days": 30, "status": "released", "source_type": "synthetic"},
    ]
    recalls = [
        {"recall_id": "RCL-001", "batch_id": "BATCH-004", "sku_id": "SKU-005", "supplier_id": "SUP-001",
         "reason": "Supplier quality hold: pack label lot mismatch reported by the supplier",
         "issued_on": (base - timedelta(days=1)).isoformat(), "authority": "Supplier quality team",
         "status": "open", "required_action": "quarantine_batch", "source_type": "synthetic"},
    ]
    routes = [
        {"route_id": "RTE-001", "vehicle_label": "Van AP-09", "capacity_units": 40, "area": "Kukatpally",
         "departure_date": (base + timedelta(days=1)).isoformat(), "status": "planned", "source_type": "synthetic"},
        {"route_id": "RTE-002", "vehicle_label": "Van AP-14", "capacity_units": 60, "area": "Secunderabad",
         "departure_date": (base + timedelta(days=1)).isoformat(), "status": "planned", "source_type": "synthetic"},
    ]
    sku_orders = [row for row in open_orders if row["sku_id"] == "SKU-003"][:6]
    dispatch_rows = []
    for index, order in enumerate(sku_orders):
        route = routes[0] if index < len(sku_orders) // 2 else routes[1]
        dispatch_rows.append({
            "route_id": route["route_id"], "order_id": order["order_id"], "retailer_id": order["retailer_id"],
            "sku_id": order["sku_id"], "quantity_units": order["quantity_units"], "unit": order["unit"],
            "priority": order["priority"], "promised_date": order["requested_delivery_date"],
            "source_type": "synthetic",
        })
    write_csv(out / "retailer_credit_limits.csv", credit)
    write_csv(out / "trade_schemes.csv", schemes)
    write_csv(out / "delivery_evidence.csv", evidence)
    write_csv(out / "batch_lots.csv", batches)
    write_csv(out / "recall_notices.csv", recalls)
    write_csv(out / "dispatch_routes.csv", routes)
    write_csv(out / "dispatch_orders.csv", dispatch_rows)


def generate(out: Path, seed: int, as_of: date = date(2026, 11, 23)) -> None:
    rng = random.Random(seed)
    out.mkdir(parents=True, exist_ok=True)
    base = as_of
    state_version = "synthetic-v3-live-" + base.strftime("%Y%m%d")
    products = [{"sku_id": f"SKU-{i+1:03}", "category": cat, "product_name": cat,
                 "pack_description": pack, "base_unit": unit, "units_per_case": units,
                 "unit_cost_rupees": format(Decimal(80) + Decimal(i) * Decimal("9.25"), ".2f"),
                 "source_type": "synthetic"}
                for i, (cat, pack, unit, units) in enumerate(PRODUCTS)]
    suppliers = [{"supplier_id": f"SUP-{i+1:03}", "supplier_name": name,
                  "lead_time_days": lead_time, "payment_terms_days": terms,
                  "source_type": "synthetic"} for i, (name, lead_time, terms) in enumerate(SUPPLIERS)]
    retailers = [{"retailer_id": f"RET-{i+1:03}", "retailer_name": name, "shop_type": shop_type,
                  "area": LOCALITIES[i % len(LOCALITIES)],
                  "service_priority": ["normal", "normal", "high"][i % 3],
                  "source_type": "synthetic", "verified_business": "false"}
                 for i, (name, shop_type) in enumerate(RETAILERS)]
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
    offer_by_pair = {(offer["supplier_id"], offer["sku_id"]): offer for offer in offers}
    offers_by_supplier = {
        supplier["supplier_id"]: [offer for offer in offers if offer["supplier_id"] == supplier["supplier_id"]]
        for supplier in suppliers
    }
    deliveries = generate_historical_deliveries(50, suppliers, products, offers, rng, base, state_version)
    cash = [{"entry_id": f"CASH-{i+1:03}", "entry_date": (base - timedelta(days=29-i)).isoformat(),
             "entry_type": "inflow" if i % 3 == 0 else "outflow",
             "amount_rupees": format(
                 Decimal(25000) if i % 3 == 0 else -Decimal(rng.randint(300000, 1000000)) / 100,
                 ".2f",
             ),
             "minimum_buffer_rupees": "50000.00", "source_type": "synthetic"} for i in range(30)]
    scenarios = [
        {"scenario_id":"SCN-001","name":"Normal day","trigger":"Use starting operational state","expected":"Feasible plan or explicit infeasibility; enforce stock, supplier and cash constraints"},
        {"scenario_id":"SCN-002","name":"Biscuit demand spike","trigger":"Increase biscuit demand by 60 percent for two simulated days","expected":"Recompute stock and orders; show unmet demand and replan"},
        {"scenario_id":"SCN-003","name":"Supplier delay","trigger":"Delay one supplier by two days; balance date unknown","expected":"Compare alternatives; do not invent a revised date"},
        {"scenario_id":"SCN-004","name":"Liquidity stress","trigger":"Delay a ₹30,000.00 retailer payment by seven days","expected":"Protect the ₹50,000.00 minimum buffer or report infeasible"},
        {"scenario_id":"SCN-005","name":"Inventory discrepancy","trigger":"Physical count finds 15 fewer base units for one SKU","expected":"Reallocate without negative stock"},
        {"scenario_id":"SCN-006","name":"Retailer complaint","trigger":"Late delivery complaint with product mention but no order ID","expected":"Preserve exact evidence and request clarification for unmatched order"},
        {"scenario_id":"SCN-007","name":"Competitor report","trigger":"One uncorroborated promotion observation","expected":"Show as reported/unverified, not as established market fact"},
        {"scenario_id":"SCN-008","name":"Combined disruption","trigger":"Demand increase, supplier delay and delayed payment together","expected":"Replan under hard constraints or explain infeasibility"},
        {"scenario_id":"SCN-010","name":"Overdue retailer with new order","trigger":"Retailer with an overdue receivable places a new order","expected":"Show exposure and hold for human credit review; no credit decision"},
        {"scenario_id":"SCN-011","name":"Scheme claim mismatch","trigger":"Retailer claims a promotion that does not match the approved scheme register","expected":"Compare claim with scheme terms; no discount or credit note executed"},
        {"scenario_id":"SCN-012","name":"Short and damaged delivery","trigger":"Received quantity, damage and wrong-item count differ from the purchase order","expected":"Show delivery variance and raise a supplier claim for human approval"},
        {"scenario_id":"SCN-013","name":"Batch recall and quality hold","trigger":"Supplier issues a quality hold for one batch","expected":"Quarantine affected batch and block allocation; human approval only"},
        {"scenario_id":"SCN-014","name":"Short-dated stock and return window","trigger":"Batch expires inside the supplier return window","expected":"Recommend return or priority dispatch; no stock mutation"},
        {"scenario_id":"SCN-015","name":"Dispatch under vehicle capacity","trigger":"Route demand exceeds vehicle capacity","expected":"Allocate by priority and promised date; list deferred orders"},
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
        "state_version": state_version,
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
        text = template.format(
            product=product["product_name"],
            retailer=retailer["retailer_name"],
            supplier=supplier["supplier_name"],
        )
        evidence = next((word for word in ("late", "damaged", "short", "asking", "scheme", "delay", "not verified", "no quantity") if word in text.lower()), "")
        is_supplier_update = intent == "supplier_delay"
        entities = {
            "product": product["product_name"],
            "retailer_id": None if is_supplier_update else retailer["retailer_id"],
            "retailer_name": None if is_supplier_update else retailer["retailer_name"],
            "supplier_id": supplier["supplier_id"] if is_supplier_update else None,
            "supplier_name": supplier["supplier_name"] if is_supplier_update else None,
        }
        messages.append({"message_id": f"MSG-{i+1:05}", "source_type": "synthetic" if intent not in ("supplier_delay",) else "supplier_update",
                         "observed_at": f"{(base - timedelta(days=29 - (i % 28))).isoformat()}T10:00:00+05:30", "language": "English",
                         "text": text, "intent": intent, "entities": json.dumps(entities),
                         "urgency": "unclear" if i % 5 == 0 else "normal", "evidence_span": evidence,
                         "uncertainty": "Synthetic example; exact order/date/quantity may be unstated.", "review_label": "correct",
                         "consent_status": "synthetic", "source_type_label": "synthetic"})
        events.append({"event_id": f"EVT-{i+1:05}", "source_message_ids": [f"MSG-{i+1:05}"],
                       "event_type": intent, "extracted_facts": [], "inferences": {},
                       "evidence_spans": [text],
                       "uncertainties": ["Synthetic annotation; order/date/quantity are not asserted unless stated in the source."],
                       "human_review_required": True, "status": "pending_review",
                       "state_version": state_version})
    with (out / "messages.jsonl").open("w", encoding="utf-8") as f:
        for row in messages:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    with (out / "events.jsonl").open("w", encoding="utf-8") as f:
        for row in events:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    (out / "DATA_DICTIONARY.md").write_text(
        "# Synthetic dataset dictionary\n\nGenerated by `scripts/generate_synthetic_data.py`; all entities and events are fictional. Reproducible with a fixed seed. Currency is exact decimal rupees with two decimal places; quantities use the explicit `unit`/`base_unit` field. Dates are ISO 8601; timestamps include +05:30. `messages.jsonl` contains 1,000 labelled synthetic examples; `events.jsonl` has corresponding evidence-linked event annotations. Keep both separate from any permissioned pilot data. `scenarios.csv/json` provide eight repeatable cases. Supplier offers are valid only for listed supplier-SKU rows. No value represents verified local prices or business activity.\n\n"
        "Supplier and retailer rows carry fictional trade names (`supplier_name`, `retailer_name`, `shop_type`, locality `area`). Names are display labels only; `supplier_id` and `retailer_id` remain the internal join keys used by orders, deliveries, facts, plans and review records. Messages quote trade names the way a person would write them, while the `entities` annotation stores both the name and the matching ID.\n\n"
        "Tables: products, suppliers, retailers, supplier_products, inventory, historical_order_lines, open_orders, supplier_deliveries, scheduled_receivables, retailer_complaints, market_observations, cash_ledger, scenarios and messages/events. Stable IDs, explicit units, two-decimal INR strings and state_version values connect related rows. Unknown source facts must remain unknown.\n\n"
        "Extended tables: `scheduled_receivables` uses `receivable_id` with a `retailer_id` foreign key and exact INR amounts; `retailer_complaints` uses `complaint_id` with `retailer_id` and `sku_id` foreign keys; `market_observations` uses `observation_id` and `source_id` with retailer/SKU scope, explicit uncertainty and corroboration status. All three carry the business state's `state_version` and `source_type: synthetic`.\n",
        encoding="utf-8")
    print(f"Generated synthetic pack at {out} (seed={seed}, messages={len(messages)}, scenarios={len(scenarios)})")
    scheduled_receivables = generate_scheduled_receivables(30, retailers, rng, base, state_version)
    retailer_complaints = generate_retailer_complaints(25, retailers, products, rng, base, state_version)
    market_observations = generate_market_observations(30, retailers, products, rng, base, state_version)

    # Write them out
    write_csv(out / "scheduled_receivables.csv", scheduled_receivables)
    write_csv(out / "retailer_complaints.csv", retailer_complaints)
    write_csv(out / "market_observations.csv", market_observations)
    generate_advisory_tables(out, base, state_version, retailers, open_orders)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=20261105)
    parser.add_argument("--as-of", type=date.fromisoformat, default=date(2026, 11, 23))
    parser.add_argument("--out", type=Path, default=Path("data/synthetic"))
    args = parser.parse_args()
    generate(args.out, args.seed, args.as_of)
