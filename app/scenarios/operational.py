import hashlib
from datetime import date
from decimal import Decimal

from app.agents.supplier import build_supplier_options
from app.decision import recommend_plan
from app.extraction.base import Extraction
from app.optimization.baseline import build_view_candidate_plans, select_best_plan
from app.optimization.context import build_planning_view
from app.scenarios.contracts import ScenarioFixture, ScenarioOverlays
from app.schemas.contracts import AgentResult, BusinessEvent, BusinessState, MessageSubmission, Recommendation
from app.units import format_units
from app.verification.checks import verify_scenario_plan


def _stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:12]
    return f"{prefix}-{digest}"


def _clarification(message: MessageSubmission, event: BusinessEvent, extraction: Extraction, reason: str) -> dict:
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
        "review_kind": "triage",
        "trace": ["received", "event_extracted", "needs_clarification"],
        "mode": extraction.mode,
    }


def overlays_for_message(
    intent: str,
    extraction: Extraction,
    state: BusinessState,
    sku_id: str,
    fixture: ScenarioFixture | None,
) -> ScenarioOverlays:
    if fixture:
        return fixture.overlays
    inventory = next(row for row in state.inventory if row["sku_id"] == sku_id)
    if intent == "supplier_delay":
        return ScenarioOverlays(
            original_supplier_id=extraction.fact("supplier_id").value,
            supplier_delay_days=int(extraction.fact("delay_days").value),
            delayed_incoming_units=inventory["incoming_units"],
        )
    if intent == "demand_spike":
        percent = extraction.fact("demand_uplift_percent")
        if percent is None:
            raise ValueError("Demand uplift percentage is required")
        return ScenarioOverlays(demand_multiplier=Decimal("1") + Decimal(percent.value) / Decimal("100"))
    if intent == "stock_discrepancy":
        count = extraction.fact("physical_count_units")
        if count is None:
            raise ValueError("Reported physical count is required")
        return ScenarioOverlays(physical_count_delta=int(count.value) - inventory["on_hand_units"])
    if intent == "combined_disruption":
        raise ValueError("Combined disruption requires an explicit scenario fixture")
    return ScenarioOverlays()


def _agent_results(state: BusinessState, view, unit: str) -> list[dict]:
    retailers = {row["retailer_id"]: row for row in state.retailers}
    inventory_row = next(row for row in state.inventory if row["sku_id"] == view.sku_id)
    demand = sum(row["quantity_units"] for row in view.orders)
    inventory = AgentResult(
        agent_name="inventory",
        status="ok",
        state_version=state.state_version,
        proposal={
            "sku_id": view.sku_id,
            "unit": unit,
            "on_hand_units": inventory_row["on_hand_units"],
            "book_on_hand_units": view.book_on_hand_units,
            "counted_on_hand_units": view.counted_on_hand_units,
            "reserved_units": inventory_row["reserved_units"],
            "incoming_units": inventory_row["incoming_units"],
            "delayed_incoming_units": inventory_row["incoming_units"]
            + inventory_row["on_hand_units"]
            - inventory_row["reserved_units"]
            - view.immediate_available_units
            if view.book_on_hand_units == view.counted_on_hand_units
            else 0,
            "immediately_available_units": view.immediate_available_units,
            "open_demand_units": demand,
            "shortage_units": max(0, demand - view.immediate_available_units),
            "immediate_shortage_units": max(0, demand - view.immediate_available_units),
            "reorder_required": inventory_row["on_hand_units"] <= inventory_row["reorder_point_units"],
        },
        evidence_refs=[f"inventory:{view.sku_id}", state.state_version],
    )
    affected = [
        {
            **row,
            "retailer_name": retailers.get(row["retailer_id"], {}).get("retailer_name", ""),
            "area": retailers.get(row["retailer_id"], {}).get("area", ""),
        }
        for row in view.orders
    ]
    orders = AgentResult(
        agent_name="orders",
        status="ok",
        state_version=state.state_version,
        proposal={
            "sku_id": view.sku_id,
            "affected_orders": affected,
            "affected_order_count": len(affected),
            "total_requested_units": demand,
            "unit": unit,
        },
        evidence_refs=[f"order:{row['order_id']}" for row in view.orders],
    )
    return [inventory.model_dump(mode="json"), orders.model_dump(mode="json")]


def run_operational_scenario(
    message: MessageSubmission,
    event: BusinessEvent,
    extraction: Extraction,
    state: BusinessState,
    fixture: ScenarioFixture | None = None,
    decision_mode: str = "deterministic",
) -> dict:
    intent = event.event_type
    sku_id = (fixture.target_sku_id if fixture else None) or extraction.inferences.get("catalogue_sku_id")
    if not sku_id:
        return _clarification(message, event, extraction, "An unambiguous product and pack is required.")
    try:
        overlays = overlays_for_message(intent, extraction, state, sku_id, fixture)
        view = build_planning_view(state, sku_id, overlays)
    except (ValueError, KeyError) as exc:
        return _clarification(message, event, extraction, str(exc))

    product = next(row for row in state.products if row["sku_id"] == sku_id)
    unit = product["base_unit"]
    demand = sum(row["quantity_units"] for row in view.orders)
    required = max(0, demand - view.immediate_available_units)
    options = build_supplier_options(
        state,
        sku_id,
        required,
        view.original_supplier_id or "",
        view.supplier_delay_days,
        view.planning_horizon,
    )
    candidates, exclusions = build_view_candidate_plans(view, options)
    candidate_verifications = {
        plan.candidate_id: verify_scenario_plan(state, plan, overlays, sku_id)
        for plan in candidates
    }
    verified_candidates = [
        plan for plan in candidates if candidate_verifications[plan.candidate_id].valid
    ]
    failed_candidates = [
        plan for plan in candidates if not candidate_verifications[plan.candidate_id].valid
    ]
    for plan in failed_candidates:
        exclusions.append(
            {
                "candidate_id": plan.candidate_id,
                "supplier_id": plan.supplier_option.supplier_id if plan.supplier_option else None,
                "reasons": list(candidate_verifications[plan.candidate_id].violations),
                "details": {"verification": "failed"},
            }
        )
    selected, decision_record = recommend_plan(
        decision_mode,
        verified_candidates,
        message,
        event.model_dump(mode="json"),
        view.original_supplier_id,
        state.as_of.date(),
    )
    verification = candidate_verifications[selected.candidate_id] if selected else None
    if selected is None and decision_record.get("abstain_reason"):
        event.uncertainties.append(decision_record["abstain_reason"])

    assumptions = [
        "Scenario arrival dates are planning estimates, not supplier-confirmed commitments.",
        "Candidate procurement costs are immediate outflows; dated receipts are explicit simulation inputs.",
    ]
    if view.overlay_audit:
        assumptions.append("Scenario overlays are applied once to copies; base business state is unchanged.")
    if overlays.demand_multiplier != 1:
        assumptions.append("Demand uplift is rounded upward per affected order line, not on aggregate demand.")
    if overlays.physical_count_delta is not None:
        assumptions.append("The reported physical count is unverified; book stock is preserved for reconciliation.")
    if fixture:
        assumptions.extend(f"Simulation input: {key}={value}" for key, value in fixture.assumptions.items())
    for unknown in fixture.unknowns if fixture else []:
        if unknown not in event.uncertainties:
            event.uncertainties.append(unknown)
    event.inferences["scenario_planning_horizon"] = view.planning_horizon.isoformat()
    event.inferences["scenario_overlay_count"] = str(len(view.overlay_audit))

    warnings = []
    if selected and selected.late_units:
        warnings.append(f"{format_units(selected.late_units, unit)} remain late in the selected plan.")
    if selected and selected.unmet_units:
        warnings.append(f"{format_units(selected.unmet_units, unit)} remain unmet; no feasible candidate covers all demand.")
    if verification and not verification.valid:
        warnings.extend(verification.violations)
    if selected is None:
        for plan in failed_candidates:
            for violation in candidate_verifications[plan.candidate_id].violations:
                if violation not in warnings:
                    warnings.append(violation)

    option = selected.supplier_option if selected else None
    if selected is None:
        mode_label = "Policy-grounded LLM" if decision_mode == "policy_grounded_llm" else "Deterministic"
        summary = f"{mode_label} mode returned no verified eligible recommendation. Human review is required."
    elif option:
        label = option.supplier_name or option.supplier_id
        qty = option.quantity_units
        quantity_label = format_units(qty, unit)
        fulfilment = (
            "all requested"
            if selected.unmet_units == 0
            else f"{selected.fulfilled_units} of {selected.total_requested_units} requested"
        )
        summary = (
            f"Recommended option: buy {quantity_label} from {label} ({option.supplier_id}). "
            f"It fulfils {fulfilment} units, with {selected.late_units} arriving after the promised date "
            f"and {selected.unmet_units} unfilled. Awaiting human review."
        )
    else:
        fulfilment = (
            "all requested"
            if selected.unmet_units == 0
            else f"{selected.fulfilled_units} of {selected.total_requested_units} requested"
        )
        summary = (
            f"Stock alone fulfils {fulfilment} units, with {selected.late_units} arriving after the promised "
            f"date and {selected.unmet_units} unfilled. Awaiting human review."
        )
    recommendation = Recommendation(
        recommendation_id=_stable_id("rec", event.event_id, selected.candidate_id if selected else decision_mode),
        state_version=state.state_version,
        summary=summary,
        evidence_refs=[message.message_id, state.state_version],
        assumptions=assumptions,
        warnings=warnings,
        review_status="pending_review" if verification and verification.valid else "needs_clarification",
    )
    trace = [
        "received",
        "state_loaded",
        "event_extracted",
        "specialists_completed",
        "candidates_optimized",
        "candidate_plans_verified",
    ]
    if selected is None:
        trace.append("verification_failed" if candidates and not verified_candidates else "decision_abstained")
    else:
        trace.append("decision_recommended")
        trace.append("pending_human_review" if verification and verification.valid else "verification_failed")
    result = {
        "message": message.model_dump(mode="json"),
        "event": event.model_dump(mode="json"),
        "scenario_id": fixture.scenario_id if fixture else None,
        "review_kind": "operational_plan",
        "agent_results": _agent_results(state, view, unit),
        "scenario_view": {
            "sku_id": sku_id,
            "unit": unit,
            "book_on_hand_units": view.book_on_hand_units,
            "counted_on_hand_units": view.counted_on_hand_units,
            "scenario_usable_units": view.immediate_available_units,
            "opening_cash_rupees": str(view.opening_cash_rupees),
            "planning_horizon": view.planning_horizon.isoformat(),
            "overlays": list(view.overlay_audit),
        },
        "supplier_options": [option.model_dump(mode="json") for option in options],
        "candidate_plans": [plan.model_dump(mode="json") for plan in candidates],
        "excluded_candidates": [
            exclusion.model_dump(mode="json") if hasattr(exclusion, "model_dump") else dict(exclusion)
            for exclusion in exclusions
        ],
        "selected_plan": selected.model_dump(mode="json") if selected else None,
        "verification": verification.model_dump(mode="json") if verification else None,
        "decision": decision_record,
        "decision_mode": decision_mode,
        "recommendation": recommendation.model_dump(mode="json"),
        "counterfactuals": [],
        "trace": trace,
        "mode": extraction.mode,
    }
    if view.receipts and selected:
        counter_candidates, counter_exclusions = build_view_candidate_plans(view, options, "on_time")
        counter_selected = select_best_plan(counter_candidates)
        counter_verification = verify_scenario_plan(state, counter_selected, overlays, sku_id, "on_time")
        result["counterfactuals"].append(
            {
                "name": "receipts_on_time",
                "candidate_plans": [plan.model_dump(mode="json") for plan in counter_candidates],
                "excluded_candidates": [row.model_dump(mode="json") for row in counter_exclusions],
                "selected_plan": counter_selected.model_dump(mode="json"),
                "verification": counter_verification.model_dump(mode="json"),
            }
        )
    return result
