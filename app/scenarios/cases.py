import hashlib

from app.extraction.base import Extraction
from app.scenarios.contracts import ScenarioFixture
from app.schemas.contracts import BusinessEvent, BusinessState, MessageSubmission, Recommendation


def _stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:12]
    return f"{prefix}-{digest}"


def run_case_scenario(
    message: MessageSubmission,
    event: BusinessEvent,
    extraction: Extraction,
    state: BusinessState,
    fixture: ScenarioFixture | None = None,
) -> dict:
    sender = message.sender
    retailer_fact = extraction.fact("retailer_id")
    retailer_id = retailer_fact.value if retailer_fact else sender.party_id if sender and sender.party_type == "retailer" else None
    sku_id = (fixture.target_sku_id if fixture else None) or extraction.inferences.get("catalogue_sku_id")
    order_reference = extraction.fact("order_reference")
    orders = fixture.history if fixture and fixture.history else state.open_orders
    matches = [
        dict(row)
        for row in orders
        if (not retailer_id or row.get("retailer_id") == retailer_id)
        and (not sku_id or row.get("sku_id") == sku_id)
        and row.get("status", "open") == "open"
    ]
    if order_reference:
        matches = [row for row in matches if row.get("order_id") == order_reference.value]

    clarification_slot = None
    if not retailer_id:
        clarification_slot = "retailer_id"
    elif not sku_id:
        clarification_slot = "product"
    elif len(matches) != 1:
        clarification_slot = "order_reference"

    event.status = "needs_clarification" if clarification_slot else "pending_review"
    for unknown in fixture.unknowns if fixture else []:
        if unknown not in event.uncertainties:
            event.uncertainties.append(unknown)

    case_context = {
        "issue_type": event.event_type,
        "retailer_id": retailer_id,
        "sku_id": sku_id,
        "matched_orders": matches,
        "matched_order_count": len(matches),
        "clarification_slot": clarification_slot,
        "operational_action_executed": False,
    }
    if clarification_slot == "order_reference" and matches:
        reason = "Multiple orders match this complaint; an order reference is required."
        summary = "Order reference required before delivery follow-up: " + ", ".join(
            row["order_id"] for row in matches
        )
    elif clarification_slot:
        reason = f"Complaint review requires {clarification_slot.replace('_', ' ')}."
        summary = reason
    else:
        reason = None
        order = matches[0]
        summary = (
            f"Review {event.event_type.replace('_', ' ')} for {order['order_id']}; verify delivery evidence "
            "and obtain human approval before any retailer response or operational action."
        )
    if reason:
        event.uncertainties.append(reason)

    recommendation = Recommendation(
        recommendation_id=_stable_id("rec", event.event_id, clarification_slot or "case"),
        state_version=state.state_version,
        summary=summary,
        evidence_refs=[message.message_id] + [f"order:{row['order_id']}" for row in matches],
        assumptions=["Complaint details are reported, not independently verified."],
        warnings=[reason] if reason else ["No outbound response, refund, replacement, or stock mutation is executed."],
        review_status="needs_clarification" if clarification_slot else "pending_review",
    )
    return {
        "message": message.model_dump(mode="json"),
        "event": event.model_dump(mode="json"),
        "scenario_id": fixture.scenario_id if fixture else None,
        "review_kind": "case_review",
        "case_context": case_context,
        "question": (
            "Which order reference is this complaint about? Matching orders: "
            + ", ".join(row["order_id"] for row in matches)
            if clarification_slot == "order_reference" and matches
            else None
        ),
        "candidate_plans": [],
        "excluded_candidates": [],
        "selected_plan": None,
        "verification": None,
        "recommendation": recommendation.model_dump(mode="json"),
        "trace": [
            "received",
            "state_loaded",
            "event_extracted",
            "case_assessed",
            "needs_clarification" if clarification_slot else "pending_human_review",
        ],
        "mode": extraction.mode,
    }
