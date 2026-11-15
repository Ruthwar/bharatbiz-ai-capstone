import hashlib

from app.agents.orders import analyze_fulfilment, available_by_sku
from app.extraction.base import Extraction
from app.scenarios.contracts import ScenarioFixture
from app.schemas.contracts import BusinessEvent, BusinessState, MessageSubmission, Recommendation


def _stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:12]
    return f"{prefix}-{digest}"


def _response(
    message: MessageSubmission,
    event: BusinessEvent,
    extraction: Extraction,
    fixture: ScenarioFixture | None,
    market_context: dict,
    summary: str,
    evidence_refs: list[str],
) -> dict:
    event.status = "pending_review"
    for unknown in fixture.unknowns if fixture else []:
        if unknown not in event.uncertainties:
            event.uncertainties.append(unknown)
    recommendation = Recommendation(
        recommendation_id=_stable_id("rec", event.event_id, market_context["signal_type"]),
        state_version=message.state_version,
        summary=summary,
        evidence_refs=list(dict.fromkeys([message.message_id, *evidence_refs])),
        assumptions=[
            "Market observations are reported and unverified; they are not measured demand or confirmed competitor terms.",
            "No pricing, procurement, catalogue, assortment, or outbound-message action is executed.",
        ],
        warnings=["Human verification is required before using this signal in an operational decision."],
        review_status="pending_review",
    )
    return {
        "message": message.model_dump(mode="json"),
        "event": event.model_dump(mode="json"),
        "scenario_id": fixture.scenario_id if fixture else None,
        "review_kind": "market_signal_review",
        "market_context": market_context,
        "candidate_plans": [],
        "excluded_candidates": [],
        "selected_plan": None,
        "verification": None,
        "recommendation": recommendation.model_dump(mode="json"),
        "trace": ["received", "state_loaded", "event_extracted", "signal_assessed", "pending_human_review"],
        "mode": extraction.mode,
    }


def run_competitor_observation(
    message: MessageSubmission,
    event: BusinessEvent,
    extraction: Extraction,
    state: BusinessState,
    fixture: ScenarioFixture | None = None,
) -> dict:
    observations = [dict(row) for row in fixture.observations] if fixture else []
    if not observations:
        observations = [{
            "observation_id": message.message_id,
            "reporter_id": message.sender.party_id if message.sender else None,
            "reported_at": message.observed_at.isoformat(),
            "observation_text": message.text,
            "source_message_id": message.message_id,
        }]

    unique = []
    seen = set()
    for row in observations:
        fingerprint = (
            row.get("reporter_id"),
            row.get("competitor_name"),
            row.get("product_label"),
            row.get("offer"),
            row.get("area"),
            row.get("observation_text"),
        )
        if fingerprint not in seen:
            seen.add(fingerprint)
            unique.append(row)
    reporters = {row.get("reporter_id") for row in unique if row.get("reporter_id")}
    corroboration = "corroborated_unverified" if len(reporters) >= 2 else "single_reporter_unverified"
    context = {
        "signal_type": "competitor_observation",
        "observations": unique,
        "unique_observation_count": len(unique),
        "distinct_reporter_count": len(reporters),
        "corroboration": corroboration,
        "verification_status": "reported_unverified",
        "operational_action_executed": False,
    }
    summary = (
        f"Reported competitor signal: {len(unique)} unique reports from {len(reporters)} distinct reporters; "
        f"{corroboration.replace('_', ' ')}. Review evidence only; no competitive action is recommended automatically."
    )
    return _response(
        message,
        event,
        extraction,
        fixture,
        context,
        summary,
        [row.get("source_message_id", row["observation_id"]) for row in unique],
    )


def run_product_request(
    message: MessageSubmission,
    event: BusinessEvent,
    extraction: Extraction,
    state: BusinessState,
    fixture: ScenarioFixture | None = None,
) -> dict:
    requests = [dict(row) for row in (fixture.history + fixture.observations)] if fixture else []
    if not requests:
        requests = [{
            "request_id": message.message_id,
            "retailer_id": message.sender.party_id if message.sender else None,
            "reported_at": message.observed_at.isoformat(),
            "product_label": extraction.fact("product").value if extraction.fact("product") else message.text,
            "request_count": 1,
            "source_message_id": message.message_id,
        }]
    labels = [row.get("product_label", "") for row in requests]
    product_label = next((label for label in labels if label), message.text)
    catalogue_labels = {
        f"{row['product_name']} {row['pack_description']}".casefold(): row["sku_id"] for row in state.products
    }
    matched_sku = extraction.inferences.get("catalogue_sku_id") or catalogue_labels.get(product_label.casefold())
    retailers = {row.get("retailer_id") for row in requests if row.get("retailer_id")}
    request_count = sum(int(row.get("request_count", 1)) for row in requests)
    stock_check = {"status": "no_catalogue_match", "matched_sku_id": None}
    if matched_sku:
        fulfilment = analyze_fulfilment(state, matched_sku)
        summary_row = fulfilment.by_sku[0] if fulfilment.by_sku else None
        stock_check = {
            "status": "indicative_only",
            "matched_sku_id": matched_sku,
            "available_units": available_by_sku(state).get(matched_sku, 0),
            "allocated_to_open_orders_units": summary_row.allocated_units if summary_row else 0,
            "unallocated_units": (
                summary_row.free_after_allocation_units
                if summary_row
                else available_by_sku(state).get(matched_sku, 0)
            ),
            "verification_violations": fulfilment.verification_violations,
            "order_confirmed": False,
            "incoming_stock_included": False,
        }
    context = {
        "signal_type": "smaller_pack_request",
        "requested_product_label": product_label,
        "requests": requests,
        "distinct_retailer_count": len(retailers),
        "reported_request_count": request_count,
        "catalogue_match": matched_sku is not None,
        "matched_sku_id": matched_sku,
        "stock_check": stock_check,
        "verification_status": "reported_unverified",
        "assortment_changed": False,
        "operational_action_executed": False,
    }
    availability = "No existing catalogue pack match was found." if not matched_sku else f"Existing catalogue match: {matched_sku}."
    summary = (
        f"Reported pack request from {len(retailers)} retailers with {request_count} reported requests. "
        f"{availability} Aggregate and verify demand; do not infer supplier availability or change assortment automatically."
    )
    return _response(
        message,
        event,
        extraction,
        fixture,
        context,
        summary,
        [row.get("source_message_id", row["request_id"]) for row in requests],
    )
