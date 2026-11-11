"""Reviewer-facing explanation of a planned recommendation. Pure data, no rendering."""


def build_review_context(result: dict) -> dict | None:
    """Summarise why a candidate won so a reviewer can check the reasoning, not just the outcome."""
    selected = result.get("selected_plan")
    if not selected:
        return None

    agents = {
        row.get("agent_name"): row.get("proposal", {}) for row in result.get("agent_results") or []
    }
    inventory = agents.get("inventory", {})
    orders = agents.get("orders", {})
    recommendation = result.get("recommendation") or {}
    event = result.get("event") or {}
    verification = result.get("verification") or {}

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
        "source_text": (result.get("message") or {}).get("text", ""),
        "evidence": event.get("extracted_facts", []),
        "assumptions": recommendation.get("assumptions", []),
        "unknowns": event.get("uncertainties", []),
        "warnings": recommendation.get("warnings", []),
        "verification_valid": bool(verification.get("valid")),
        "verification_violations": verification.get("violations", []),
        "allocations": selected.get("allocations", []),
    }
