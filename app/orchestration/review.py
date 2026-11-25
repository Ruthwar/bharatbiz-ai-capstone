"""Reviewer-facing explanation of a planned recommendation. Pure data, no rendering."""

from datetime import date
from decimal import Decimal

from app.decision.selector import policy_context, policy_inventory
from app.rag.retrieval import retrieve
from app.units import format_units

EVENT_LABELS = {
    "baseline": "Normal trading day",
    "demand_spike": "Demand spike",
    "supplier_delay": "Supplier delay",
    "limited_cash": "Cash constraint",
    "stock_discrepancy": "Stock-count mismatch",
    "combined_disruption": "Combined disruption",
    "delivery_complaint": "Delivery complaint",
    "damaged_item": "Damaged item report",
    "missing_item": "Missing item report",
    "product_request": "Product request",
    "scheme_question": "Scheme question",
    "competitor_observation": "Competitor report",
    "credit_check": "Credit check",
    "scheme_claim": "Scheme claim",
    "delivery_discrepancy": "Delivery discrepancy",
    "batch_recall": "Batch recall",
    "short_dated_stock": "Short-dated stock",
    "dispatch_planning": "Dispatch planning",
    "other": "Other message",
    "unclassified": "Unclassified message",
}
MODE_LABELS = {
    "deterministic": "Deterministic · no model",
    "policy_grounded_llm": "Policy-grounded LLM",
}
REVIEW_LABELS = {
    "operational_plan": "Procurement plan",
    "decision_abstention": "No plan recommended",
    "case_review": "Complaint review",
    "market_signal_review": "Market signal review",
    "credit_review": "Credit review",
    "scheme_claim_review": "Scheme claim review",
    "delivery_discrepancy_review": "Delivery discrepancy review",
    "recall_review": "Recall review",
    "expiry_review": "Expiry review",
    "dispatch_review": "Dispatch review",
    "triage": "Triage only",
}
EXTRACTION_LABELS = {
    "llm": "language-model extraction",
    "rules": "rule-based extraction",
}

_REFERENCE_QUERY = {
    "supplier_delay": (
        "supplier delay handling policy revised confirmed date late units headroom cash buffer affordability"
    ),
}
_DEFAULT_REFERENCE_QUERY = "human review triage evidence policy procedure"


def _rupees(value) -> str:
    return f"₹{Decimal(str(value)):,.2f}"


def _units(value, unit: str) -> str:
    return format_units(value, unit)


def _fact_summary(facts: list[dict], limit: int = 4) -> str:
    parts = []
    for fact in facts[:limit]:
        field = str(fact.get("field", "")).replace("_", " ")
        value = str(fact.get("value", "")).strip()
        if field and value:
            parts.append(f"{field} = {value}")
    return ", ".join(parts)


def _reference_row(reference: dict, relation: str) -> dict:
    return {
        "document_id": reference["document_id"],
        "title": reference["title"],
        "section": reference.get("section") or "Document overview",
        "quote": reference["quote"],
        "effective_from": reference["effective_from"],
        "version": reference.get("version"),
        "licence": reference["licence"],
        "source_url": reference.get("source_url"),
        "classification": reference.get("classification"),
        "relation": relation,
    }


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
    return [_reference_row(hit, "reference") for hit in hits], None


def _decision_inputs(result: dict, event: dict) -> tuple[str | None, date | None]:
    supplier_id = next(
        (fact.get("value") for fact in event.get("extracted_facts") or [] if fact.get("field") == "supplier_id"),
        None,
    )
    observed = (result.get("message") or {}).get("observed_at")
    try:
        as_of = date.fromisoformat(observed[:10]) if observed else None
    except ValueError:
        as_of = None
    return supplier_id, as_of


def _operational_policy_basis(result: dict, event: dict) -> tuple[list[dict], list[dict], str | None]:
    """Policies that actually govern this decision, marked cited or in force."""
    decision = result.get("decision") or {}
    retrieved = decision.get("retrieved_policies") or []
    supplier_id, as_of = _decision_inputs(result, event)
    pending: list[dict] = []
    if as_of is not None:
        try:
            pending = policy_inventory(event.get("event_type"), supplier_id, as_of)["not_yet_effective"]
        except Exception:
            pending = []
    if retrieved:
        cited = set(decision.get("citations") or [])
        basis = [
            _reference_row(reference, "cited" if reference["document_id"] in cited else "retrieved")
            for reference in retrieved
        ]
        return basis, pending, None
    if as_of is None:
        return [], pending, "policy basis unavailable: the message has no usable decision date"
    try:
        context = policy_context(event.get("event_type"), supplier_id, as_of)
    except Exception as exc:
        return [], pending, f"policy basis unavailable: {type(exc).__name__}"
    return [_reference_row(passage, "in_force") for passage in context["passages"]], pending, None


def _case_market_policy_basis(result: dict, event: dict) -> tuple[list[dict], list[dict], str | None]:
    """Show the rules in force for a complaint or market review, and any approved rules still pending."""
    supplier_id, as_of = _decision_inputs(result, event)
    if as_of is None:
        references, error = _policy_references(result, event)
        return references, [], error
    try:
        pending = policy_inventory(event.get("event_type"), supplier_id, as_of)["not_yet_effective"]
        context = policy_context(event.get("event_type"), supplier_id, as_of)
    except Exception:
        references, error = _policy_references(result, event)
        return references, [], error
    return [_reference_row(passage, "in_force") for passage in context["passages"]], pending, None


def _message_step(result: dict, label: str) -> dict:
    message = result.get("message") or {}
    sender = message.get("sender") or {}
    who = " ".join(
        part for part in (sender.get("party_type", "").capitalize(), sender.get("party_id", "")) if part
    ) or "an unidentified sender"
    observed = (message.get("observed_at") or "")[:10]
    reader = EXTRACTION_LABELS.get(result.get("mode"), "deterministic extraction")
    detail = f"Message from {who}" + (f" on {observed}" if observed else "") + f", read with {reader}."
    if label:
        detail += f" It concerns a {label.lower()}."
    return {"title": "Message received", "detail": detail, "status": "done", "substeps": []}


def _event_step(facts: list[dict], uncertainties: list[str], label: str) -> dict:
    detail = f"Classified as {label.lower()}."
    summary = _fact_summary(facts)
    if summary:
        detail += f" Facts captured: {summary}."
    if uncertainties:
        detail += f" {len(uncertainties)} point(s) remain open and are shown under Evidence."
    return {"title": "Event understood", "detail": detail, "status": "done", "substeps": []}


def _operational_steps(result: dict, context: dict, selected: bool) -> list[dict]:
    unit = context["unit"]
    facts = context["evidence"]
    event = result.get("event") or {}
    steps = [
        _message_step(result, context["event_label"]),
        _event_step(facts, event.get("uncertainties") or [], context["event_label"]),
    ]

    if context["required_units"]:
        stock_detail = (
            f"{context['order_count']} open orders need {_units(context['requested_units'], unit)}. "
            f"{_units(context['usable_units'], unit)} are free from stock now, so "
            f"{_units(context['required_units'], unit)} must come from a purchase."
        )
    else:
        stock_detail = (
            f"{context['order_count']} open orders need {_units(context['requested_units'], unit)}, and "
            f"{_units(context['usable_units'], unit)} are free from stock now. No purchase is required."
        )
    steps.append({"title": "Stock and orders checked", "detail": stock_detail, "status": "done", "substeps": []})

    supplier_options = [row for row in context["alternatives"] if row["quantity_units"]]
    option_lines = [
        f"{row['label']}: buy {_units(row['quantity_units'], unit)}, estimated arrival "
        f"{row['arrival_date'] or 'from stock now'}, cost {_rupees(row['total_cost_rupees'])}."
        for row in supplier_options
    ]
    steps.append(
        {
            "title": "Supply options priced",
            "detail": (
                f"{len(context['alternatives'])} options were built: stock only plus "
                f"{len(supplier_options)} supplier option(s). Each carries a quantity, estimated arrival, "
                "full cost and projected cash impact."
            ),
            "status": "done",
            "substeps": option_lines,
        }
    )

    excluded = context["excluded_candidates"]
    checks_detail = (
        f"{len(context['alternatives'])} option(s) passed the independent recheck of units, cost, "
        "cash buffer and totals."
    )
    if excluded:
        checks_detail += (
            f" {len(excluded)} further option(s) were removed with a recorded reason, such as a cash-buffer "
            "breach or an ineligible supplier."
        )
    steps.append({"title": "Every plan rechecked", "detail": checks_detail, "status": "done", "substeps": []})

    decision = context.get("decision") or {}
    references = context.get("references") or []
    pending = context.get("pending_policies") or []
    if context["decision_mode"] == "policy_grounded_llm":
        doc_ids = ", ".join(reference["document_id"] for reference in references) or "none"
        substeps = [
            f"Retrieved {len(references)} policy passage(s) in force for this event, supplier and decision date: {doc_ids}.",
            "Left out policy documents that are not approved, not in scope for this supplier, or not yet in force.",
            f"Gave the model the verified facts and {len(context['alternatives'])} verified option(s) and asked for one "
            "choice or an explicit abstention.",
            "Checked that every citation exists in the retrieved set and that the stated priority cites its policy.",
            "Rejected any choice whose stated priority contradicts the numbers or that another plan matches or beats.",
            "Wrote the explanation from verified figures; the model did not calculate units, dates or costs.",
        ]
        if pending:
            upcoming = ", ".join(
                f"{item['document_id']} from {item['effective_from']}" for item in pending
            )
            substeps.append(f"Newer policy document(s) exist but are not in force yet: {upcoming}.")
        detail = "The model selected from policies that apply today. The application then checked the answer."
    else:
        detail = (
            "Policy passages are attached for context. The fixed ranking, not the policy text, selected the option."
        )
        substeps = [
            "Comparison order: fewest unfilled units → fewest late units → earliest estimated arrival → "
            "lowest cost → candidate ID.",
        ]
        if pending:
            upcoming = ", ".join(
                f"{item['document_id']} from {item['effective_from']}" for item in pending
            )
            substeps.append(f"Written but not yet in force on this date: {upcoming}.")
    steps.append(
        {"title": "Policy rules applied", "detail": detail, "status": "done", "substeps": substeps}
    )

    if selected:
        choice = next((row for row in context["alternatives"] if row["selected"]), None)
        label = choice["label"] if choice else context["selected_candidate_id"]
        detail = (
            f"{label} was chosen. It fulfils {context['selected_fulfilled_units']} of "
            f"{_units(context['requested_units'], unit)}, leaves {context['selected_unmet_units']} unfilled and "
            f"{context['selected_late_units']} arriving after the promised date"
        )
        if context.get("selected_arrival_date"):
            detail += f", with an estimated arrival of {context['selected_arrival_date']}"
        detail += f". Purchase cost is {_rupees(context['selected_cost_rupees'])}."
        priority = str(decision.get("priority") or "").strip()
        if context["decision_mode"] == "policy_grounded_llm" and priority:
            detail += f" The model stated the priority as {priority.replace('_', ' and ')}."
        steps.append({"title": "Plan selected", "detail": detail, "status": "done", "substeps": []})
        steps.append(
            {
                "title": "Waiting for a person",
                "detail": (
                    "Nothing has been purchased, paid or messaged. Approving records this choice in the review "
                    "ledger only; rejecting or editing it changes nothing in the business data."
                ),
                "status": "waiting",
                "substeps": [],
            }
        )
    else:
        reason = (
            decision.get("abstain_reason")
            or "; ".join(context.get("verification_violations") or [])
            or "No verified option was eligible."
        )
        steps.append(
            {
                "title": "Selection stopped",
                "detail": f"No option was selected: {reason}",
                "status": "blocked",
                "substeps": [],
            }
        )
        steps.append(
            {
                "title": "A person decides next",
                "detail": (
                    "The system did not fall back to a different mode or guess. A reviewer must resolve the "
                    "issue and rerun the case."
                ),
                "status": "waiting",
                "substeps": [],
            }
        )
    return steps


def _operational_summary(context: dict, selected: bool) -> str:
    unit = context["unit"]
    decision = context.get("decision") or {}
    if not selected:
        reason = (
            decision.get("abstain_reason")
            or "; ".join(context.get("verification_violations") or [])
            or "no verified option was eligible"
        )
        return (
            f"No plan is recommended for this {context['event_label'].lower()}. {reason} "
            "Nothing in the business data has changed."
        )
    choice = next((row for row in context["alternatives"] if row["selected"]), None)
    parts = [
        f"Across {context['order_count']} open orders, {_units(context['requested_units'], unit)} are needed "
        f"and {_units(context['usable_units'], unit)} are free from stock, leaving "
        f"{_units(context['required_units'], unit)} to buy."
    ]
    if choice and choice["quantity_units"]:
        parts.append(
            f"The recommended option is {choice['label']}: buy {_units(choice['quantity_units'], unit)}, "
            f"estimated arrival {choice['arrival_date']}, cost {_rupees(choice['total_cost_rupees'])}."
        )
    else:
        parts.append("Stock alone is enough; no purchase is recommended.")
    parts.append(
        f"It fulfils {context['selected_fulfilled_units']} of "
        f"{_units(context['requested_units'], unit)}, leaves {context['selected_unmet_units']} unfilled and "
        f"{context['selected_late_units']} arriving after the promised date, and keeps "
        f"{_rupees(choice['headroom_rupees']) if choice else 'the cash buffer'} above the minimum cash buffer."
    )
    return " ".join(parts)


def _case_steps(result: dict, context: dict) -> list[dict]:
    case = context["case_context"]
    steps = [
        _message_step(result, context["event_label"]),
        _event_step(context["evidence"], (result.get("event") or {}).get("uncertainties") or [], context["event_label"]),
    ]
    match_detail = (
        f"{case['matched_order_count']} order(s) match this report"
        + (f" for {case['sku_id']}" if case.get("sku_id") else " and the product is still unresolved")
        + "."
    )
    steps.append({"title": "Order book checked", "detail": match_detail, "status": "done", "substeps": []})
    if case.get("clarification_slot"):
        detail = (
            f"One detail is missing ({case['clarification_slot'].replace('_', ' ')}), so the system asked a "
            "follow-up question instead of guessing."
        )
        status = "waiting"
    else:
        detail = "The case is ready for a person to review. No refund, replacement or reply has been sent."
        status = "waiting"
    steps.append({"title": "Human review", "detail": detail, "status": status, "substeps": []})
    return steps


def _market_steps(result: dict, context: dict) -> list[dict]:
    market = context["market_context"]
    steps = [
        _message_step(result, context["event_label"]),
        _event_step(context["evidence"], (result.get("event") or {}).get("uncertainties") or [], context["event_label"]),
    ]
    if market.get("signal_type") == "competitor_observation":
        checked = (
            f"{market['unique_observation_count']} unique report(s) came from "
            f"{market['distinct_reporter_count']} distinct reporter(s); corroboration is "
            f"{market['corroboration'].replace('_', ' ')}."
        )
    else:
        checked = (
            f"{market['reported_request_count']} request(s) came from "
            f"{market['distinct_retailer_count']} distinct retailer(s). Catalogue match: "
            f"{'yes' if market['catalogue_match'] else 'no'}."
        )
    steps.append({"title": "Reports compared", "detail": checked, "status": "done", "substeps": []})
    steps.append(
        {
            "title": "Human review",
            "detail": (
                "The signal stays reported and unverified. No price, stock, assortment or customer response "
                "is executed automatically."
            ),
            "status": "waiting",
            "substeps": [],
        }
    )
    return steps


def _case_summary(context: dict) -> str:
    case = context["case_context"]
    retailer = case.get("retailer_id") or "A retailer"
    product = case.get("sku_id") or "an unidentified product"
    if case.get("clarification_slot"):
        return (
            f"{retailer} reports a {context['event_label'].lower()} for {product}. "
            f"{case['matched_order_count']} orders match, so the system asked for the "
            f"{case['clarification_slot'].replace('_', ' ')} before continuing. No reply, refund or stock "
            "change has been made."
        )
    return (
        f"{retailer} reports a {context['event_label'].lower()} for {product}, matched to "
        f"{case['matched_order_count']} order(s). A person must review the case; no reply, refund or stock "
        "change has been made."
    )


def _market_summary(context: dict) -> str:
    market = context["market_context"]
    if market.get("signal_type") == "competitor_observation":
        return (
            f"{market['unique_observation_count']} report(s) from {market['distinct_reporter_count']} distinct "
            "reporters describe a competitor move. The information is corroborated but unverified, so no price "
            "or stock response is triggered."
        )
    return (
        f"{market['reported_request_count']} request(s) from {market['distinct_retailer_count']} retailers "
        "are recorded. "
        + ("A catalogue product matches, but availability is only indicative. " if market.get("catalogue_match")
           else "No catalogue product matches this pack. ")
        + "No order, price or assortment change has been made."
    )


def build_review_context(result: dict) -> dict | None:
    """Summarise the evidence and trade-offs behind any reviewable outcome."""
    event = result.get("event") or {}
    recommendation = result.get("recommendation") or {}
    verification = result.get("verification") or {}
    decision = result.get("decision") or {}
    decision_mode = result.get("decision_mode", "deterministic")
    event_type = event.get("event_type") or "unclassified"
    shared = {
        "review_kind": result.get("review_kind"),
        "review_label": REVIEW_LABELS.get(result.get("review_kind"), "Review"),
        "decision_mode": decision_mode,
        "decision_mode_label": MODE_LABELS.get(decision_mode, decision_mode.replace("_", " ").title()),
        "extraction_mode": result.get("mode"),
        "extraction_label": EXTRACTION_LABELS.get(result.get("mode"), "deterministic extraction"),
        "decision": decision,
        "scenario_id": result.get("scenario_id"),
        "event_type": event_type,
        "event_label": EVENT_LABELS.get(event_type, event_type.replace("_", " ").title()),
        "source_text": (result.get("message") or {}).get("text", ""),
        "evidence": event.get("extracted_facts", []),
        "assumptions": recommendation.get("assumptions", []),
        "unknowns": event.get("uncertainties", []),
        "warnings": recommendation.get("warnings", []),
        "references": [],
        "policy_basis": [],
        "pending_policies": [],
        "references_error": None,
        "retail_context": result.get("retail_context"),
        "decision_steps": [],
        "operator_summary": "",
    }

    if result.get("advisory_context") is not None:
        advisory = result["advisory_context"]
        if decision.get("retrieved_policies"):
            references, pending, references_error = _operational_policy_basis(result, event)
        else:
            references, pending, references_error = _case_market_policy_basis(result, event)
            references = [{**reference, "relation": "reference"} for reference in references]
        steps = list(advisory.get("decision_steps") or [])
        if references or pending:
            documents = ", ".join(reference["document_id"] for reference in references) or "none"
            if decision_mode == "policy_grounded_llm":
                step_title = "Policy rules checked"
                detail = (
                    f"{len(references)} policy passage(s) were retrieved for this event, party and decision date "
                    f"and grounded the selection: {documents}."
                )
            else:
                step_title = "Policy rules listed, not applied"
                detail = (
                    f"{len(references)} policy passage(s) are in force for this event, party and decision date: "
                    f"{documents}. The fixed ranking never reads them; they are listed only so a reviewer can "
                    "compare the rule with the choice."
                )
            if pending:
                detail += " Newer documents are written but not yet in force."
            steps.insert(
                len(steps) - 1,
                {"title": step_title, "detail": detail, "status": "done", "substeps": []},
            )
        context = {
            **shared,
            "advisory_context": advisory,
            "verification_valid": None,
            "references": references,
            "policy_basis": references,
            "pending_policies": pending,
            "references_error": references_error,
            "operator_summary": advisory.get("operator_summary", ""),
            "decision_steps": steps,
        }
        return context

    if result.get("case_context") is not None:
        references, pending, references_error = _case_market_policy_basis(result, event)
        context = {
            **shared,
            "case_context": result["case_context"],
            "question": result.get("question"),
            "verification_valid": None,
            "references": references,
            "policy_basis": references,
            "pending_policies": pending,
            "references_error": references_error,
        }
        context["operator_summary"] = _case_summary(context)
        context["decision_steps"] = _case_steps(result, context)
        return context

    if result.get("market_context") is not None:
        references, pending, references_error = _case_market_policy_basis(result, event)
        context = {
            **shared,
            "market_context": result["market_context"],
            "verification_valid": None,
            "references": references,
            "policy_basis": references,
            "pending_policies": pending,
            "references_error": references_error,
        }
        context["operator_summary"] = _market_summary(context)
        context["decision_steps"] = _market_steps(result, context)
        return context

    basis, pending, basis_error = _operational_policy_basis(result, event)
    base = {
        **shared,
        "references": basis,
        "policy_basis": basis,
        "pending_policies": pending,
        "references_error": basis_error,
    }

    selected = result.get("selected_plan")
    if not selected:
        if result.get("review_kind") != "operational_plan":
            return None
        context = {
            **base,
            "review_kind": "decision_abstention",
            "candidate_plans": result.get("candidate_plans") or [],
            "excluded_candidates": result.get("excluded_candidates") or [],
            "verification_valid": None,
        }
        context["operator_summary"] = _operational_summary(
            {
                **context,
                "unit": "unit",
                "order_count": 0,
                "requested_units": 0,
                "usable_units": 0,
                "required_units": 0,
                "alternatives": [],
            },
            False,
        )
        context["decision_steps"] = _abstention_steps(result, context)
        return context

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

    context = {
        **base,
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
        "verification_valid": bool(verification.get("valid")),
        "verification_violations": verification.get("violations", []),
        "allocations": selected.get("allocations", []),
        "cash_schedule": selected.get("cash_projection", {}).get("daily_schedule", []),
    }
    context["operator_summary"] = _operational_summary(context, True)
    context["decision_steps"] = _operational_steps(result, context, True)
    return context


def _abstention_steps(result: dict, context: dict) -> list[dict]:
    steps = [
        _message_step(result, context["event_label"]),
        _event_step(context["evidence"], (result.get("event") or {}).get("uncertainties") or [], context["event_label"]),
    ]
    excluded = context.get("excluded_candidates") or []
    steps.append(
        {
            "title": "Options checked",
            "detail": (
                f"{len(context.get('candidate_plans') or [])} option(s) were priced and {len(excluded)} removed "
                "with a recorded reason before selection."
            ),
            "status": "done",
            "substeps": [],
        }
    )
    decision = context.get("decision") or {}
    reason = (
        decision.get("abstain_reason")
        or "; ".join((result.get("verification") or {}).get("violations", []))
        or "No verified option was eligible."
    )
    steps.append(
        {
            "title": "Selection stopped",
            "detail": f"No option was selected: {reason}",
            "status": "blocked",
            "substeps": [],
        }
    )
    steps.append(
        {
            "title": "A person decides next",
            "detail": (
                "The system did not fall back to a different mode or guess. A reviewer must resolve the issue "
                "and rerun the case."
            ),
            "status": "waiting",
            "substeps": [],
        }
    )
    return steps
