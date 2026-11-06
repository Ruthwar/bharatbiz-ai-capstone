import hashlib
import re
from datetime import date
from pathlib import Path

from app.agents.inventory import analyze_inventory
from app.agents.orders import analyze_orders
from app.agents.supplier import build_supplier_options
from app.optimization.baseline import build_candidate_plans, select_best_plan
from app.schemas.contracts import (
    BusinessEvent,
    BusinessState,
    EvidenceFact,
    MessageSubmission,
    Recommendation,
)
from app.state import load_business_state
from app.verification.checks import verify_plan

RULES = (
    ("supplier_delay", re.compile(r"delay|late|postpon", re.I)),
    ("delivery_complaint", re.compile(r"delivery|delivered|arriv", re.I)),
    ("product_request", re.compile(r"request|need|asking|pack", re.I)),
    ("scheme_question", re.compile(r"scheme|offer|discount", re.I)),
    ("competitor_observation", re.compile(r"competitor|nearby shop", re.I)),
)
DELAY_PATTERN = re.compile(
    r"\b(\d+|one|two|three|four|five|six|seven|eight|nine|ten)[-\s]days?\s+delay\b",
    re.I,
)
DAY_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}


def _stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:12]
    return f"{prefix}-{digest}"


def _fact(field: str, value: str, text: str, start: int, end: int) -> EvidenceFact:
    return EvidenceFact(
        field=field,
        value=value,
        evidence_span=text[start:end],
        span_start=start,
        span_end=end,
    )


def _base_event(message: MessageSubmission, event_type: str) -> BusinessEvent:
    return BusinessEvent(
        event_id=_stable_id("evt", message.message_id, message.text, message.state_version),
        source_message_ids=[message.message_id],
        event_type=event_type,
        uncertainties=["Product, quantity, date or business reference not asserted unless explicitly extracted."],
        state_version=message.state_version,
    )


def _resolve_product(state: BusinessState, text: str) -> dict | None:
    full_matches = []
    category_matches = []
    for product in state.products:
        full_label = f"{product['product_name']} {product['pack_description']}"
        full_match = re.search(re.escape(full_label), text, re.I)
        if full_match:
            full_matches.append((product, full_label, full_match))
        category_match = re.search(rf"\b{re.escape(product['product_name'])}\b", text, re.I)
        if category_match:
            category_matches.append((product, product["product_name"], category_match))

    matches = full_matches or category_matches
    sku_ids = {product["sku_id"] for product, _, _ in matches}
    if len(sku_ids) != 1:
        return None
    product, label, match = matches[0]
    return {
        "sku_id": product["sku_id"],
        "unit": product["base_unit"],
        "label": label,
        "start": match.start(),
        "end": match.end(),
        "match_type": "product_and_pack" if full_matches else "product_name",
    }


def _clarification_response(message: MessageSubmission, event: BusinessEvent, reason: str) -> dict:
    event.status = "needs_clarification"
    event.uncertainties.append(reason)
    recommendation = Recommendation(
        recommendation_id=_stable_id("rec", event.event_id, "clarification"),
        state_version=message.state_version,
        summary="Clarification is required before operational planning.",
        evidence_refs=[message.message_id],
        warnings=[reason],
        review_status="needs_clarification",
    )
    return {
        "message": message.model_dump(mode="json"),
        "event": event.model_dump(mode="json"),
        "recommendation": recommendation.model_dump(mode="json"),
        "candidate_plans": [],
        "selected_plan": None,
        "verification": None,
        "trace": ["received", "event_extracted", "needs_clarification"],
        "mode": "rules_mock",
    }


def _process_supplier_delay(message: MessageSubmission, event: BusinessEvent, data_dir: Path | None) -> dict:
    state = load_business_state(data_dir=data_dir, expected_version=message.state_version)
    supplier_match = re.search(r"\b(SUP-\d{3})\b", message.text, re.I)
    delay_match = DELAY_PATTERN.search(message.text)
    product = _resolve_product(state, message.text)

    if supplier_match:
        event.extracted_facts.append(
            _fact("supplier_id", supplier_match.group(1).upper(), message.text, *supplier_match.span(1))
        )
    if delay_match:
        raw_delay = delay_match.group(1).lower()
        delay_days = int(raw_delay) if raw_delay.isdigit() else DAY_WORDS[raw_delay]
        delay_span = message.text[delay_match.start():delay_match.end()].split()[0]
        delay_start = delay_match.start()
        delay_end = delay_start + len(delay_span)
        event.extracted_facts.append(
            _fact("delay_days", str(delay_days), message.text, delay_start, delay_end)
        )
    if product:
        event.extracted_facts.append(
            _fact("product", product["label"], message.text, product["start"], product["end"])
        )
        event.inferences["catalogue_sku_id"] = product["sku_id"]

    missing = []
    if not supplier_match:
        missing.append("supplier reference")
    if not delay_match:
        missing.append("delay duration")
    if not product:
        missing.append("an unambiguous product and pack")
    if missing:
        return _clarification_response(
            message,
            event,
            "Unable to resolve " + ", ".join(missing) + " from the source and synthetic catalogue.",
        )

    event.uncertainties = [
        "Supplier-confirmed revised delivery date is unknown.",
        "Source-stated delayed quantity is unknown.",
        "Purchase-order reference is unknown.",
    ]

    inventory_row = next(row for row in state.inventory if row["sku_id"] == product["sku_id"])
    delayed_incoming_units = inventory_row["incoming_units"]
    inventory = analyze_inventory(state, product["sku_id"], delayed_incoming_units)
    orders = analyze_orders(state, product["sku_id"])
    affected = orders.proposal["affected_orders"]
    planning_horizon = max(
        (date.fromisoformat(row["requested_delivery_date"]) for row in affected),
        default=state.as_of.date(),
    )
    event.inferences["scenario_planning_horizon"] = planning_horizon.isoformat()
    event.inferences["delayed_incoming_assumption"] = (
        f"{delayed_incoming_units} {product['unit']} units from {supplier_match.group(1).upper()}"
    )

    required_units = max(
        orders.proposal["total_requested_units"] - inventory.proposal["immediately_available_units"],
        0,
    )
    supplier_options = build_supplier_options(
        state,
        product["sku_id"],
        required_units,
        supplier_match.group(1).upper(),
        delay_days,
        planning_horizon,
    )
    candidates = build_candidate_plans(
        state,
        product["sku_id"],
        inventory.proposal["immediately_available_units"],
        supplier_options,
        planning_horizon,
    )
    selected = select_best_plan(candidates)
    verification = verify_plan(state, selected, inventory.proposal["immediately_available_units"])

    assumptions = inventory.assumptions + [
        "Scenario arrival dates are planning estimates, not supplier-confirmed commitments.",
        "Candidate procurement costs are immediate outflows with no additional inflows assumed.",
    ]
    warnings = []
    if selected.late_units:
        warnings.append(f"{selected.late_units} {product['unit']} units remain late in the selected plan.")
    if selected.unmet_units:
        warnings.append(f"{selected.unmet_units} {product['unit']} units remain unmet in the selected plan.")
    if not verification.valid:
        warnings.extend(verification.violations)

    if selected.supplier_option:
        option = selected.supplier_option
        summary = (
            f"Recommended scenario option: {option.quantity_units} {product['unit']} units from "
            f"{option.supplier_id}; {selected.fulfilled_units}/{selected.total_requested_units} fulfilled, "
            f"{selected.late_units} late, {selected.unmet_units} unmet. Awaiting human review."
        )
    else:
        summary = (
            f"Use available stock: {selected.fulfilled_units}/{selected.total_requested_units} fulfilled, "
            f"{selected.late_units} late, {selected.unmet_units} unmet. Awaiting human review."
        )

    recommendation = Recommendation(
        recommendation_id=_stable_id("rec", event.event_id, selected.candidate_id),
        state_version=state.state_version,
        summary=summary,
        evidence_refs=[message.message_id, state.state_version],
        assumptions=assumptions,
        warnings=warnings,
        review_status="pending_review" if verification.valid else "needs_clarification",
    )
    return {
        "message": message.model_dump(mode="json"),
        "event": event.model_dump(mode="json"),
        "agent_results": [inventory.model_dump(mode="json"), orders.model_dump(mode="json")],
        "supplier_options": [option.model_dump(mode="json") for option in supplier_options],
        "candidate_plans": [plan.model_dump(mode="json") for plan in candidates],
        "selected_plan": selected.model_dump(mode="json"),
        "verification": verification.model_dump(mode="json"),
        "recommendation": recommendation.model_dump(mode="json"),
        "trace": [
            "received",
            "state_loaded",
            "event_extracted",
            "specialists_completed",
            "candidates_optimized",
            "independently_verified",
            "pending_human_review",
        ],
        "mode": "rules_mock",
    }


def process_message(message: MessageSubmission, data_dir: Path | None = None) -> dict:
    event_type = next((name for name, pattern in RULES if pattern.search(message.text)), "other")
    event = _base_event(message, event_type)
    if event_type == "supplier_delay":
        return _process_supplier_delay(message, event, data_dir)

    match = next((match for _, pattern in RULES if (match := pattern.search(message.text))), None)
    if match:
        event.extracted_facts.append(
            _fact("trigger_phrase", match.group(0), message.text, match.start(), match.end())
        )
    return {
        "message": message.model_dump(mode="json"),
        "event": event.model_dump(mode="json"),
        "mode": "rules_mock",
    }
