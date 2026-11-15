"""Reviewer-facing explanation of a planned recommendation. Pure data, no rendering."""

from datetime import date

from app.rag.retrieval import retrieve

_REFERENCE_QUERY = {
    "supplier_delay": (
        "supplier delay revised confirmed date late units accepted headroom buffer excluded case"
    ),
}
_DEFAULT_REFERENCE_QUERY = "human review triage evidence policy procedure"


def _policy_references(result: dict, event: dict) -> tuple[list[dict], str | None]:
    """Retrieve the rules behind the plan. Citations explain the decision; they never feed the arithmetic."""
    query = _REFERENCE_QUERY.get(event.get("event_type"), _DEFAULT_REFERENCE_QUERY)
    facts = " ".join(str(fact.get("value", "")) for fact in event.get("extracted_facts") or [])
    observed = (result.get("message") or {}).get("observed_at")
    supplier_id = next(
        (fact.get("value") for fact in event.get("extracted_facts") or [] if fact.get("field") == "supplier_id"),
        None,
    )
    try:
        hits = retrieve(
            f"{query} {facts}".strip(),
            top_k=3,
            supplier_id=supplier_id,
            as_of=date.fromisoformat(observed[:10]) if observed else None,
        )
    except Exception as exc:  # a broken index must not hide the review card
        return [], f"policy references unavailable: {type(exc).__name__}"
    return [
        {
            "document_id": hit["document_id"],
            "title": hit["title"],
            "section": hit["heading"],
            "quote": hit["quote"],
            "effective_from": hit["effective_from"],
            "licence": hit["licence"],
            "source_url": hit["source_url"],
            "classification": hit["classification"],
        }
        for hit in hits
    ], None


def build_review_context(result: dict) -> dict | None:
    """Summarise the evidence and trade-offs behind any reviewable outcome."""
    event = result.get("event") or {}
    recommendation = result.get("recommendation") or {}
    verification = result.get("verification") or {}
    references, references_error = _policy_references(result, event)
    shared = {
        "review_kind": result.get("review_kind"),
        "scenario_id": result.get("scenario_id"),
        "source_text": (result.get("message") or {}).get("text", ""),
        "evidence": event.get("extracted_facts", []),
        "assumptions": recommendation.get("assumptions", []),
        "unknowns": event.get("uncertainties", []),
        "warnings": recommendation.get("warnings", []),
        "references": references,
        "references_error": references_error,
        "retail_context": result.get("retail_context"),
    }
    if result.get("case_context") is not None:
        return {
            **shared,
            "case_context": result["case_context"],
            "question": result.get("question"),
            "verification_valid": None,
        }
    if result.get("market_context") is not None:
        return {
            **shared,
            "market_context": result["market_context"],
            "verification_valid": None,
        }

    selected = result.get("selected_plan")
    if not selected:
        return None

    agents = {
        row.get("agent_name"): row.get("proposal", {}) for row in result.get("agent_results") or []
    }
    inventory = agents.get("inventory", {})
    orders = agents.get("orders", {})

    requested = orders.get("total_requested_units", 0)
    usable = inventory.get("immediately_available_units", 0)

    alternatives = []
    for plan in result.get("candidate_plans") or []:
        option = plan.get("supplier_option")
        if option and option.get("supplier_name"):
            label = f"{option['supplier_name']} ({option['supplier_id']})"
        elif option:
            label = option["supplier_id"]
        else:
            label = "Stock only"
        alternatives.append(
            {
                "candidate_id": plan["candidate_id"],
                "label": label,
                "selected": plan["candidate_id"] == selected["candidate_id"],
                "quantity_units": option.get("quantity_units", 0) if option else 0,
                "arrival_date": option.get("scenario_arrival_date") if option else None,
                "total_cost_rupees": plan["total_cost_rupees"],
                "fulfilled_units": plan["fulfilled_units"],
                "late_units": plan["late_units"],
                "unmet_units": plan["unmet_units"],
                "ending_cash_rupees": plan["cash_projection"]["ending_cash_rupees"],
                "headroom_rupees": plan["cash_projection"]["headroom_rupees"],
            }
        )

    return {
        **shared,
        "unit": inventory.get("unit", "unit"),
        "order_count": orders.get("affected_order_count", 0),
        "requested_units": requested,
        "usable_units": usable,
        "required_units": max(requested - usable, 0),
        "selected_candidate_id": selected["candidate_id"],
        "selected_fulfilled_units": selected["fulfilled_units"],
        "selected_late_units": selected["late_units"],
        "selected_unmet_units": selected["unmet_units"],
        "selected_arrival_date": (selected.get("supplier_option") or {}).get("scenario_arrival_date"),
        "selected_cost_rupees": selected["total_cost_rupees"],
        "alternatives": alternatives,
        "excluded_candidates": result.get("excluded_candidates", []),
        "counterfactuals": result.get("counterfactuals", []),
        "scenario_view": result.get("scenario_view"),
        "source_text": (result.get("message") or {}).get("text", ""),
        "evidence": event.get("extracted_facts", []),
        "assumptions": recommendation.get("assumptions", []),
        "unknowns": event.get("uncertainties", []),
        "warnings": recommendation.get("warnings", []),
        "verification_valid": bool(verification.get("valid")),
        "verification_violations": verification.get("violations", []),
        "allocations": selected.get("allocations", []),
        "cash_schedule": selected.get("cash_projection", {}).get("daily_schedule", []),
        "references": references,
        "references_error": references_error,
    }
