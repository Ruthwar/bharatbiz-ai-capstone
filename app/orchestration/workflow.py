import hashlib
import logging
from datetime import date
from pathlib import Path

from app.agents.inventory import analyze_inventory
from app.agents.orders import analyze_orders
from app.agents.supplier import build_supplier_options
from app.extraction import configured_extractor, validate_extraction
from app.extraction.base import Extraction
from app.extraction.llm import ExtractionError
from app.extraction.rules import RulesExtractor
from app.optimization.baseline import build_candidate_plans, select_best_plan
from app.orchestration import router
from app.orchestration.taxonomy import TAXONOMY_VERSION, UNCLASSIFIED
from app.schemas.contracts import (
    BusinessEvent,
    BusinessState,
    EvidenceFact,
    MessageSubmission,
    Recommendation,
)
from app.state import load_business_state
from app.verification.checks import verify_plan

logger = logging.getLogger(__name__)


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


def _extract(message: MessageSubmission, state: BusinessState) -> Extraction:
    extractor = configured_extractor()
    if extractor.name == "rules":
        extraction = extractor.extract(message, state)
        validate_extraction(extraction, message, state)
        return extraction

    try:
        extraction = extractor.extract(message, state)
        violations = validate_extraction(extraction, message, state)
        if violations:
            raise ExtractionError("; ".join(violations))
        return extraction
    except Exception as exc:
        logger.warning(
            "extraction_fallback extractor=%s message_id=%s reason=%s",
            extractor.name,
            message.message_id,
            type(exc).__name__,
        )
        fallback = RulesExtractor().extract(message, state)
        validate_extraction(fallback, message, state)
        fallback.uncertainties.append(
            "Model extraction was unavailable or failed validation; deterministic rules were used."
        )
        return fallback


def _base_event(message: MessageSubmission, extraction: Extraction) -> BusinessEvent:
    return BusinessEvent(
        event_id=_stable_id("evt", message.message_id, message.text, message.state_version),
        source_message_ids=[message.message_id],
        event_type=extraction.primary_intent,
        intents=extraction.intents,
        taxonomy_version=TAXONOMY_VERSION,
        extracted_facts=list(extraction.facts),
        inferences=dict(extraction.inferences),
        uncertainties=["Product, quantity, date or business reference not asserted unless explicitly extracted."],
        state_version=message.state_version,
    )


def _clarification_response(
    message: MessageSubmission, event: BusinessEvent, extraction: Extraction, reason: str
) -> dict:
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
        "mode": extraction.mode,
    }


def _process_supplier_delay(
    message: MessageSubmission,
    event: BusinessEvent,
    extraction: Extraction,
    state: BusinessState,
    data_dir: Path | None = None,
) -> dict:
    supplier_fact = extraction.fact("supplier_id")
    delay_fact = extraction.fact("delay_days")
    sku_id = extraction.inferences.get("catalogue_sku_id")
    product_row = next((row for row in state.products if row["sku_id"] == sku_id), None)

    missing = []
    if not supplier_fact:
        missing.append("supplier reference")
    if not delay_fact:
        missing.append("delay duration")
    if not product_row:
        missing.append("an unambiguous product and pack")
    if missing:
        return _clarification_response(
            message,
            event,
            extraction,
            "Unable to resolve " + ", ".join(missing) + " from the source and synthetic catalogue.",
        )

    supplier_id = supplier_fact.value
    supplier_label = next(
        (
            f"{row['supplier_name']} ({supplier_id})"
            for row in state.suppliers
            if row["supplier_id"] == supplier_id and row.get("supplier_name")
        ),
        supplier_id,
    )
    delay_days = int(delay_fact.value)
    unit = product_row["base_unit"]

    event.uncertainties = [
        "Supplier-confirmed revised delivery date is unknown.",
        "Source-stated delayed quantity is unknown.",
        "Purchase-order reference is unknown.",
    ] + [item for item in extraction.uncertainties if item not in event.uncertainties]

    inventory_row = next(row for row in state.inventory if row["sku_id"] == sku_id)
    delayed_incoming_units = inventory_row["incoming_units"]
    inventory = analyze_inventory(state, sku_id, delayed_incoming_units)
    orders = analyze_orders(state, sku_id)
    affected = orders.proposal["affected_orders"]
    planning_horizon = max(
        (date.fromisoformat(row["requested_delivery_date"]) for row in affected),
        default=state.as_of.date(),
    )
    event.inferences["scenario_planning_horizon"] = planning_horizon.isoformat()
    event.inferences["delayed_incoming_assumption"] = (
        f"{delayed_incoming_units} {unit} units from {supplier_label}"
    )

    required_units = max(
        orders.proposal["total_requested_units"] - inventory.proposal["immediately_available_units"],
        0,
    )
    supplier_options = build_supplier_options(
        state,
        sku_id,
        required_units,
        supplier_id,
        delay_days,
        planning_horizon,
    )
    candidates = build_candidate_plans(
        state,
        sku_id,
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
        warnings.append(f"{selected.late_units} {unit} units remain late in the selected plan.")
    if selected.unmet_units:
        warnings.append(f"{selected.unmet_units} {unit} units remain unmet in the selected plan.")
    if not verification.valid:
        warnings.extend(verification.violations)

    if selected.supplier_option:
        option = selected.supplier_option
        option_label = (
            f"{option.supplier_name} ({option.supplier_id})" if option.supplier_name else option.supplier_id
        )
        summary = (
            f"Recommended scenario option: {option.quantity_units} {unit} units from "
            f"{option_label}; {selected.fulfilled_units}/{selected.total_requested_units} fulfilled, "
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
        "mode": extraction.mode,
    }


def _event_only(message: MessageSubmission, event: BusinessEvent, extraction: Extraction) -> dict:
    primary = next((match for match in extraction.intents if match.intent == event.event_type), None)
    if primary and primary.evidence_span:
        start = message.text.find(primary.evidence_span)
        if start >= 0:
            event.extracted_facts.append(
                _fact("trigger_phrase", primary.evidence_span, message.text, start, start + len(primary.evidence_span))
            )
    if event.event_type == UNCLASSIFIED:
        event.uncertainties.append("Message did not match a known intent; routed to human triage.")
    return {
        "message": message.model_dump(mode="json"),
        "event": event.model_dump(mode="json"),
        "trace": ["received", "state_loaded", "event_extracted", "routed_to_triage"],
        "mode": extraction.mode,
    }


router.register("supplier_delay", _process_supplier_delay)


def process_message(message: MessageSubmission, data_dir: Path | None = None) -> dict:
    state = load_business_state(data_dir=data_dir, expected_version=message.state_version)
    extraction = _extract(message, state)
    event = _base_event(message, extraction)
    handler = router.resolve(extraction.primary_intent)
    if handler is not None:
        result = handler(message, event, extraction, state, data_dir)
    else:
        result = _event_only(message, event, extraction)
    result["routed_action"] = router.routed_action(extraction.primary_intent)
    result["taxonomy_version"] = TAXONOMY_VERSION
    return result
