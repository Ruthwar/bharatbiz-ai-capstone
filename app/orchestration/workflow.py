import hashlib
import logging
from datetime import date
from pathlib import Path
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

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
from app.scenarios.cases import run_case_scenario
from app.scenarios.contracts import ScenarioFixture
from app.scenarios.market import run_competitor_observation, run_product_request
from app.scenarios.operational import run_operational_scenario
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


class PlanState(TypedDict, total=False):
    submission: MessageSubmission
    data_dir: Path | None
    business_state: BusinessState
    extraction: Extraction
    event: BusinessEvent
    scenario: ScenarioFixture | None
    authorized: bool
    auth_reason: str
    result: dict


# Which channel identity may report which intent. A party relaying a message is not enough.
ALLOWED_SENDERS: dict[str, tuple[str, ...]] = {
    "baseline": ("sales_rep",),
    "demand_spike": ("sales_rep",),
    "supplier_delay": ("supplier",),
    "limited_cash": ("sales_rep",),
    "stock_discrepancy": ("sales_rep",),
    "combined_disruption": ("sales_rep",),
    "delivery_complaint": ("retailer",),
    "damaged_item": ("retailer",),
    "missing_item": ("retailer",),
    "product_request": ("retailer",),
    "competitor_observation": ("sales_rep",),
}
REPORTED_PARTY_FACT: dict[str, str] = {
    "supplier_delay": "supplier_id",
    "delivery_complaint": "retailer_id",
    "damaged_item": "retailer_id",
    "missing_item": "retailer_id",
    "product_request": "retailer_id",
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
    scenario: ScenarioFixture | None = None,
) -> dict:
    if scenario is not None:
        return run_operational_scenario(message, event, extraction, state, scenario)
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


def _process_operational_scenario(
    message: MessageSubmission,
    event: BusinessEvent,
    extraction: Extraction,
    state: BusinessState,
    data_dir: Path | None = None,
    scenario: ScenarioFixture | None = None,
) -> dict:
    return run_operational_scenario(message, event, extraction, state, scenario)


def _process_case_scenario(
    message: MessageSubmission,
    event: BusinessEvent,
    extraction: Extraction,
    state: BusinessState,
    data_dir: Path | None = None,
    scenario: ScenarioFixture | None = None,
) -> dict:
    return run_case_scenario(message, event, extraction, state, scenario)


def _process_competitor_observation(
    message: MessageSubmission,
    event: BusinessEvent,
    extraction: Extraction,
    state: BusinessState,
    data_dir: Path | None = None,
    scenario: ScenarioFixture | None = None,
) -> dict:
    return run_competitor_observation(message, event, extraction, state, scenario)


def _process_product_request(
    message: MessageSubmission,
    event: BusinessEvent,
    extraction: Extraction,
    state: BusinessState,
    data_dir: Path | None = None,
    scenario: ScenarioFixture | None = None,
) -> dict:
    return run_product_request(message, event, extraction, state, scenario)


for intent in ("baseline", "demand_spike", "limited_cash", "stock_discrepancy", "combined_disruption"):
    router.register(intent, _process_operational_scenario)
for intent in ("delivery_complaint", "damaged_item", "missing_item"):
    router.register(intent, _process_case_scenario)
router.register("supplier_delay", _process_supplier_delay)
router.register("competitor_observation", _process_competitor_observation)
router.register("product_request", _process_product_request)


def _load_state(flow: PlanState) -> dict:
    submission = flow["submission"]
    return {
        "business_state": load_business_state(
            data_dir=flow.get("data_dir"), expected_version=submission.state_version
        )
    }


def _extract_node(flow: PlanState) -> dict:
    return {"extraction": _extract(flow["submission"], flow["business_state"])}


def _build_event_node(flow: PlanState) -> dict:
    return {"event": _base_event(flow["submission"], flow["extraction"])}


def _authorize(flow: PlanState) -> dict:
    """Planning needs the right sender, not just the right words. Anything else is triaged."""
    submission = flow["submission"]
    extraction = flow["extraction"]
    event = flow["event"]
    intent = extraction.primary_intent
    allowed = ALLOWED_SENDERS.get(intent)
    sender = submission.sender
    if allowed is None or sender is None:
        return {"authorized": True}

    reason = None
    if sender.party_type not in allowed:
        reason = (
            f"{intent.replace('_', ' ')} may only be reported by a {' or '.join(allowed)} account; "
            f"this message came from a {sender.party_type} account."
        )
    elif not sender.party_id and intent in REPORTED_PARTY_FACT:
        reason = "Sending account is not linked to a trade party; the report cannot be authorised."
    else:
        field = REPORTED_PARTY_FACT.get(intent)
        reported = extraction.fact(field) if field else None
        if reported and reported.value.strip().upper() != sender.party_id.strip().upper():
            reason = (
                f"Reported party {reported.value} does not match the sending account {sender.party_id}."
            )

    if reason is None:
        return {"authorized": True}

    event.uncertainties.append(reason)
    logger.warning("authorization_failed intent=%s reason=%s", intent, reason)
    return {"authorized": False, "auth_reason": reason}


def _plan_node(flow: PlanState) -> dict:
    submission = flow["submission"]
    extraction = flow["extraction"]
    event = flow["event"]
    handler = router.resolve(extraction.primary_intent)
    return {
        "result": handler(
            submission,
            event,
            extraction,
            flow["business_state"],
            flow.get("data_dir"),
            flow.get("scenario"),
        )
    }


def _triage_node(flow: PlanState) -> dict:
    result = _event_only(flow["submission"], flow["event"], flow["extraction"])
    if flow.get("authorized") is False:
        result["trace"].append("authorization_failed")
    return {"result": result}


def _after_event(flow: PlanState) -> str:
    if not router.resolve(flow["extraction"].primary_intent):
        return "triage"
    return "plan" if flow.get("authorized", True) else "triage"


def _after_plan(flow: PlanState) -> str:
    result = flow.get("result") or {}
    if result.get("selected_plan") and result.get("verification"):
        return "review_gate"
    return "finalize"


def _review_gate(flow: PlanState) -> dict:
    """A recommendation reaches a human as pending_review only when the independent check passes."""
    result = dict(flow["result"])
    verification = result.get("verification") or {}
    if verification.get("valid"):
        return {"result": result}
    recommendation = dict(result.get("recommendation") or {})
    recommendation["review_status"] = "needs_clarification"
    warnings = list(recommendation.get("warnings") or [])
    warnings.extend(item for item in verification.get("violations", []) if item not in warnings)
    recommendation["warnings"] = warnings
    result["recommendation"] = recommendation
    trace = list(result.get("trace") or [])
    if "verification_failed" not in trace:
        trace.append("verification_failed")
    result["trace"] = trace
    logger.warning(
        "verification_gate_blocked event_id=%s violations=%s",
        (result.get("event") or {}).get("event_id"),
        verification.get("violations", []),
    )
    return {"result": result}


def _finalize(flow: PlanState) -> dict:
    result = dict(flow["result"])
    if flow.get("authorized") is False:
        result["routed_action"] = "human_triage"
    else:
        result["routed_action"] = router.routed_action(flow["extraction"].primary_intent)
    result["taxonomy_version"] = TAXONOMY_VERSION
    return {"result": result}


def _build_plan_graph():
    builder = StateGraph(PlanState)
    builder.add_node("load_state", _load_state)
    builder.add_node("extract", _extract_node)
    builder.add_node("build_event", _build_event_node)
    builder.add_node("authorize", _authorize)
    builder.add_node("plan", _plan_node)
    builder.add_node("triage", _triage_node)
    builder.add_node("review_gate", _review_gate)
    builder.add_node("finalize", _finalize)

    builder.add_edge(START, "load_state")
    builder.add_edge("load_state", "extract")
    builder.add_edge("extract", "build_event")
    builder.add_edge("build_event", "authorize")
    builder.add_conditional_edges("authorize", _after_event, {"plan": "plan", "triage": "triage"})
    builder.add_conditional_edges("plan", _after_plan, {"review_gate": "review_gate", "finalize": "finalize"})
    builder.add_edge("triage", "finalize")
    builder.add_edge("review_gate", "finalize")
    builder.add_edge("finalize", END)
    return builder.compile()


plan_graph = _build_plan_graph()


def process_message(
    message: MessageSubmission,
    data_dir: Path | None = None,
    scenario: ScenarioFixture | None = None,
) -> dict:
    output = plan_graph.invoke({"submission": message, "data_dir": data_dir, "scenario": scenario})
    return output["result"]
