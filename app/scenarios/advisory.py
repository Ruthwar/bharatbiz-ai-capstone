"""Deterministic advisory reviews for policy scenarios that are not procurement plans."""

import hashlib
from datetime import date
from decimal import Decimal

from app.decision.selector import (
    policy_context,
    recommend_advisory_option,
    recommend_review_option,
)
from app.extraction.base import Extraction
from app.scenarios.advisory_data import load_advisory_tables
from app.scenarios.contracts import ScenarioFixture
from app.schemas.contracts import BusinessEvent, BusinessState, MessageSubmission, Recommendation
from app.units import format_units

NO_EXECUTION = "No credit, price, stock, dispatch or outbound-message action is executed."


def _stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:12]
    return f"{prefix}-{digest}"


def _money(value) -> str:
    return f"₹{Decimal(str(value)):,.2f}"


def _subject(fixture: ScenarioFixture | None, extraction: Extraction, *keys: str) -> dict:
    values: dict = {}
    for key in keys:
        if fixture and fixture.subject.get(key) is not None:
            values[key] = fixture.subject[key]
            continue
        fact = extraction.fact(key)
        if fact is not None:
            values[key] = fact.value
    return values


def _find(rows: list[dict], key: str, value) -> dict | None:
    return next((row for row in rows if row.get(key) == value), None)


def _recommendation(
    message: MessageSubmission,
    event: BusinessEvent,
    state: BusinessState,
    kind: str,
    summary: str,
    evidence_refs: list[str],
    assumptions: list[str],
    warnings: list[str],
    review_status: str = "pending_review",
) -> Recommendation:
    return Recommendation(
        recommendation_id=_stable_id("rec", event.event_id, kind),
        state_version=state.state_version,
        summary=summary,
        evidence_refs=list(dict.fromkeys([message.message_id, *evidence_refs, state.state_version])),
        assumptions=assumptions,
        warnings=[*warnings, NO_EXECUTION],
        review_status=review_status,
    )


def _result(
    message: MessageSubmission,
    event: BusinessEvent,
    extraction: Extraction,
    fixture: ScenarioFixture | None,
    state: BusinessState,
    kind: str,
    summary: str,
    metrics: list[dict],
    sections: list[dict],
    steps: list[dict],
    evidence_refs: list[str],
    assumptions: list[str],
    warnings: list[str],
    outcome: dict | None = None,
    options: list[dict] | None = None,
    decision: dict | None = None,
    decision_mode: str = "deterministic",
    decision_mode_applied: bool = False,
    review_status: str = "pending_review",
) -> dict:
    event.status = "pending_review"
    for unknown in fixture.unknowns if fixture else []:
        if unknown not in event.uncertainties:
            event.uncertainties.append(unknown)
    recommendation = _recommendation(
        message, event, state, kind, summary, evidence_refs, assumptions, warnings, review_status
    )
    return {
        "message": message.model_dump(mode="json"),
        "event": event.model_dump(mode="json"),
        "scenario_id": fixture.scenario_id if fixture else None,
        "review_kind": kind,
        "advisory_context": {
            "operator_summary": summary,
            "metrics": metrics,
            "sections": sections,
            "decision_steps": steps,
            "assumptions": assumptions,
            "warnings": recommendation.warnings,
            "options": options or [],
            "decision": decision or {},
            "outcome": outcome or {},
        },
        "candidate_plans": [],
        "excluded_candidates": [],
        "selected_plan": None,
        "verification": None,
        "decision": decision or {},
        "decision_mode": decision_mode,
        "decision_mode_applied": decision_mode_applied,
        "recommendation": recommendation.model_dump(mode="json"),
        "trace": ["received", "state_loaded", "event_extracted", "records_checked", "pending_human_review"],
        "mode": extraction.mode,
    }


def _opening_steps(message: MessageSubmission, event: BusinessEvent, extraction: Extraction) -> list[dict]:
    sender = message.sender
    who = " ".join(
        part for part in (sender.party_type.capitalize(), sender.party_id) if part
    ) if sender else "an unidentified sender"
    return [
        {
            "title": "Message received",
            "detail": f"Message from {who} on {message.observed_at:%Y-%m-%d}, read with {extraction.mode} extraction.",
            "status": "done",
            "substeps": [],
        },
        {
            "title": "Event understood",
            "detail": f"Classified as {event.event_type.replace('_', ' ')}. Only stated facts are used.",
            "status": "done",
            "substeps": [],
        },
    ]


def _human_step(detail: str) -> dict:
    return {"title": "Waiting for a person", "detail": detail, "status": "waiting", "substeps": []}


def _review_verdict(option: dict, selected_id: str | None) -> str:
    if selected_id and option["option_id"] == selected_id:
        return "Selected"
    if not option.get("feasible", True):
        return f"Infeasible: {option['reason']}"
    if selected_id is None:
        return "Not selected — selection stopped"
    return f"Rejected: {option['reason']}"


def _review_options_section(
    options: list[dict], infeasible: list[dict], selected_id: str | None, description: str
) -> dict:
    return {
        "title": "Options considered",
        "description": description,
        "rows": [
            {
                "Option": option["label"],
                "Effect": option.get("effect") or "—",
                "Result": _review_verdict(option, selected_id),
            }
            for option in [*options, *infeasible]
        ],
    }


def _review_tradeoff(options: list[dict], infeasible: list[dict], selected_id: str) -> str:
    others = [option for option in options if option["option_id"] != selected_id]
    if others:
        alternative = min(others, key=lambda option: int(option.get("rank", 0)))
        reason = str(alternative.get("reason") or "not preferred").rstrip(".")
        return f"Next-best {alternative['label']}: {reason}."
    if infeasible:
        return (
            f"No other feasible option was available; {infeasible[0]['label']} is infeasible: "
            f"{infeasible[0]['reason']}"
        )
    return "No other review outcome was available."


def _review_decision_section(decision: dict, options: list[dict] | None = None) -> dict:
    mode = str(decision.get("mode") or "deterministic").replace("_", " ").title()
    status = str(decision.get("status") or "recommended").replace("_", " ")
    citations = ", ".join(decision.get("citations") or []) or "none"
    selected_id = decision.get("option_id")
    selected_label = next(
        (option["label"] for option in options or [] if option["option_id"] == selected_id), selected_id
    )
    rows = [
        {"Field": "Mode", "Value": mode},
        {"Field": "Decided by", "Value": _decided_by(decision)},
        {"Field": "Role of the policies", "Value": _policy_role(decision)},
        {"Field": "Status", "Value": status},
        {"Field": "Selected outcome", "Value": selected_label or "none"},
        {"Field": "Stated priority", "Value": (decision.get("priority") or "—").replace("_", " ")},
        {"Field": "Cited policies", "Value": citations},
        {"Field": "Rationale", "Value": decision.get("rationale") or "—"},
        {"Field": "Next-best option", "Value": decision.get("tradeoff") or "—"},
    ]
    if decision.get("mode") == "policy_grounded_llm":
        description = (
            "The model confirmed one of the supplied outcomes or abstained. It cannot invent options, numbers "
            "or waive a hard policy constraint; the app checked its citations and arithmetic."
        )
    else:
        description = (
            "A fixed rule picked the outcome. No model was called and no policy passage was read; the policies "
            "shown elsewhere are for the reviewer's reference only."
        )
    return {"title": "Decision rationale", "description": description, "rows": rows}


def _decided_by(decision: dict) -> str:
    if decision.get("mode") == "policy_grounded_llm":
        model = decision.get("model")
        return f"The language model ({model})" if model else "The language model"
    return "A fixed rule (no model called)"


def _policy_role(decision: dict) -> str:
    if decision.get("mode") != "policy_grounded_llm":
        return "Reference only — they did not affect the choice."
    if decision.get("status") == "abstained":
        return "The model read them, then stopped instead of guessing."
    return "The model relied on them, and the app checked every citation."


def _grounded_review_decision(
    event: BusinessEvent,
    state: BusinessState,
    options: list[dict],
    infeasible: list[dict],
    required_citation: str,
    subject_label: str,
) -> tuple[dict | None, dict, list[dict]]:
    try:
        context = policy_context(event.event_type, None, state.as_of.date())
        references = context["passages"]
        selected_id, decision = recommend_review_option(
            event.model_dump(mode="json"),
            options,
            references,
            required_citation,
            subject_label,
            infeasible,
        )
    except Exception as exc:
        return None, {
            "mode": "policy_grounded_llm",
            "status": "abstained",
            "option_id": None,
            "priority": None,
            "rationale": "Policy retrieval failed; no review outcome was selected.",
            "tradeoff": "",
            "citations": [],
            "retrieved_policies": [],
            "abstain_reason": f"Policy retrieval failed: {type(exc).__name__}",
        }, []
    selected = next((option for option in options if option["option_id"] == selected_id), None)
    return selected, decision, references


def _review_option(
    option_id: str, label: str, effect: str, rank: int, reason: str, feasible: bool = True
) -> dict:
    option = {
        "option_id": option_id,
        "label": label,
        "effect": effect,
        "rank": rank,
        "reason": reason,
    }
    if not feasible:
        option["feasible"] = False
    return option


def _credit_review_options(
    retailer_id: str,
    limit: Decimal,
    exposure: Decimal,
    headroom: Decimal,
    open_orders: list[dict],
) -> tuple[list[dict], list[dict]]:
    options = [
        _review_option(
            "opt-hold-new-order",
            "Hold the new order for a human credit decision",
            f"No order is accepted and nothing is sent to {retailer_id}; every existing order keeps its current status.",
            0,
            "Meets the past-due review requirement without changing an existing commitment.",
        )
    ]
    if open_orders:
        listed = ", ".join(row["order_id"] for row in open_orders)
        options.append(
            _review_option(
                "opt-hold-all-orders",
                "Hold the new order and pause existing open orders",
                f"Adds a hold on {listed} without recovering any past-due amount.",
                1,
                f"Does not reduce the {_money(-headroom)} breach and delays {listed}; more restrictive than the policy requires.",
            )
        )
    infeasible = [
        _review_option(
            "opt-accept-order",
            "Accept the new order",
            f"Exposure becomes {_money(exposure)}, {_money(-headroom)} above the {_money(limit)} limit.",
            2,
            f"Exceeds the {_money(limit)} credit limit by {_money(exposure - limit)}.",
            feasible=False,
        )
    ]
    return options, infeasible


def run_credit_check(
    message: MessageSubmission,
    event: BusinessEvent,
    extraction: Extraction,
    state: BusinessState,
    fixture: ScenarioFixture | None,
    tables: dict[str, list[dict]],
    decision_mode: str = "deterministic",
) -> dict:
    subject = _subject(fixture, extraction, "retailer_id", "sku_id")
    retailer_id = subject.get("retailer_id")
    if not retailer_id and message.sender and message.sender.party_type == "retailer":
        retailer_id = message.sender.party_id
    sku_id = subject.get("sku_id") or (fixture.target_sku_id if fixture else None)
    units = int((fixture.subject.get("order_quantity_units") if fixture else 0) or 0)
    if not units and extraction.fact("quantity") is not None:
        units = int(extraction.fact("quantity").value)
    if not units and fixture is None:
        units = sum(
            int(row["quantity_units"]) for row in state.open_orders
            if row["retailer_id"] == retailer_id and row["sku_id"] == sku_id
        )
    product = _find(state.products, "sku_id", sku_id)
    unit_cost = Decimal(str(product["unit_cost_rupees"])) if product else Decimal("0")
    order_value = (unit_cost * units).quantize(Decimal("0.01"))
    receivables = tables["receivables"]
    overdue = [row for row in receivables if row["retailer_id"] == retailer_id and row["status"] == "overdue"]
    overdue_total = sum((Decimal(row["amount_rupees"]) for row in overdue), Decimal("0")).quantize(
        Decimal("0.01")
    )
    credit = _find(tables["credit_limits"], "retailer_id", retailer_id)
    limit = Decimal(credit["credit_limit_rupees"]) if credit else Decimal("0")
    exposure = (overdue_total + order_value).quantize(Decimal("0.01"))
    headroom = (limit - exposure).quantize(Decimal("0.01"))

    unit_label = product["base_unit"] if product else "unit"
    options: list[dict] = []
    infeasible: list[dict] = []
    decision_record: dict = {}
    selected: dict | None = None
    decision_mode_applied = False
    review_status = "pending_review"

    if credit is None:
        decision = "no_credit_record"
        summary = f"No credit record exists for {retailer_id}; a person must review the new order before it is accepted."
    elif overdue_total > 0 and headroom < 0:
        decision = "hold_limit_breach"
        retailer_orders = [row for row in state.open_orders if row["retailer_id"] == retailer_id]
        options, infeasible = _credit_review_options(
            retailer_id, limit, exposure, headroom, retailer_orders
        )
        decision_mode_applied = True
        if decision_mode == "policy_grounded_llm":
            selected, decision_record, _ = _grounded_review_decision(
                event, state, options, infeasible, "POL-LIQ-007", "credit review outcome"
            )
        else:
            selected = options[0]
            decision_record = {
                "mode": "deterministic",
                "status": "recommended",
                "option_id": selected["option_id"],
                "priority": "policy_requirement",
                "rationale": (
                    "Fixed rule: a new order that takes exposure above the credit limit is held. Pausing existing "
                    "orders does not recover the past-due amount and is not required; accepting the order is "
                    "infeasible. Policy passages are reference material and did not change this rule."
                ),
                "tradeoff": _review_tradeoff(options, infeasible, selected["option_id"]),
                "citations": [],
                "retrieved_policies": [],
            }
        base = (
            f"{retailer_id} already owes {_money(overdue_total)} past due. A new {format_units(units, unit_label)} "
            f"order worth {_money(order_value)} would take exposure to {_money(exposure)}, above the "
            f"{_money(limit)} limit. "
        )
        if selected is None:
            reason = decision_record.get("abstain_reason") or "No verified outcome was selected."
            summary = (
                base
                + f"Policy-grounded mode did not select a review outcome: {reason} "
                "A person must decide; nothing is accepted or sent."
            )
            review_status = "needs_clarification"
        else:
            if decision_mode == "deterministic":
                selection_note = (
                    f"A fixed rule selected: {selected['label']}. No model was called and no policy passage was "
                    "read for the choice."
                )
            else:
                cited = ", ".join(decision_record.get("citations") or []) or "no document"
                selection_note = (
                    f"The model confirmed: {selected['label']}, citing {cited}. The app checked the choice against "
                    "the supplied options and citations."
                )
            summary = base + selection_note + " A person must decide; nothing is accepted or sent."
    elif overdue_total > 0:
        decision = "hold_overdue_review"
        summary = (
            f"{retailer_id} has {_money(overdue_total)} past due. The new order adds {_money(order_value)}, "
            f"leaving {_money(headroom)} within the {_money(limit)} limit. Hold for human review rather than "
            "accepting it automatically."
        )
    else:
        decision = "clear_standard_review"
        summary = (
            f"{retailer_id} has no overdue receivables. The new order adds {_money(order_value)} against the "
            f"{_money(limit)} limit, leaving {_money(headroom)}. It can go to normal human order review."
        )

    sections = [
        {
            "title": "Credit position",
            "description": "Exposure counts the new order value plus every receivable already past due. Expected future receipts are not netted.",
            "rows": [
                {"Item": "Retailer", "Value": retailer_id},
                {"Item": "Credit limit", "Value": _money(limit) if credit else "no record"},
                {"Item": "Overdue receivables", "Value": _money(overdue_total)},
                {"Item": "New order value", "Value": f"{_money(order_value)} ({format_units(units, product['base_unit'] if product else 'unit')})"},
                {"Item": "Total exposure", "Value": _money(exposure) if credit else "not assessed"},
                {"Item": "Limit headroom", "Value": _money(headroom) if credit else "not assessed"},
            ],
        },
        {
            "title": "Past-due invoices considered",
            "description": "Only receivables marked overdue for this retailer are counted.",
            "rows": [
                {
                    "Receivable": row["receivable_id"],
                    "Due date": row["due_date"],
                    "Amount": _money(row["amount_rupees"]),
                    "Status": row["status"],
                }
                for row in overdue
            ] or [{"Receivable": "None", "Due date": "—", "Amount": _money(0), "Status": "no overdue items"}],
        },
    ]
    steps = _opening_steps(message, event, extraction) + [
        {
            "title": "Credit records checked",
            "detail": f"{len(receivables)} receivable(s) were read for {retailer_id}; {len(overdue)} are past due.",
            "status": "done",
            "substeps": [],
        },
    ]
    metrics = [
        {"label": "Past due", "value": _money(overdue_total), "note": "Not netted against new orders", "tone": "danger" if overdue_total else "success"},
        {"label": "New order", "value": _money(order_value), "note": format_units(units, unit_label), "tone": "warning"},
        {"label": "Limit headroom", "value": _money(headroom) if credit else "—", "note": "After this order", "tone": "success" if headroom >= 0 else "danger"},
    ]
    if decision_mode_applied:
        sections.append(
            _review_options_section(
                options,
                infeasible,
                selected["option_id"] if selected else None,
                (
                    "The limit breach compares holding the order, pausing existing orders and accepting the order. "
                    "Every option is shown with its effect and outcome; no option changes a recorded balance."
                ),
            )
        )
        sections.append(_review_decision_section(decision_record, options))
        steps.append(
            {
                "title": "Options compared",
                "detail": (
                    f"{len(options)} feasible review outcome(s) and {len(infeasible)} infeasible option(s) were compared."
                    if selected
                    else f"{len(options)} feasible review outcome(s) were compared; none was selected."
                ),
                "status": "done",
                "substeps": [
                    f"{option['label']} — "
                    + _review_verdict(option, selected["option_id"] if selected else None)
                    for option in [*options, *infeasible]
                ],
            }
        )
        if selected:
            steps.append(
                {
                    "title": "Policy-grounded check" if decision_mode == "policy_grounded_llm" else "Fixed rule applied",
                    "detail": (
                        f"The model confirmed {selected['label']} citing "
                        f"{', '.join(decision_record.get('citations') or [])}."
                        if decision_mode == "policy_grounded_llm"
                        else "The fixed past-due rule selected the outcome; policy passages are reference material."
                    ),
                    "status": "done",
                    "substeps": [],
                }
            )
        else:
            steps.append(
                {
                    "title": "Selection stopped",
                    "detail": (
                        "No review outcome was selected: "
                        f"{decision_record.get('abstain_reason') or 'No verified outcome was selected.'}"
                    ),
                    "status": "blocked",
                    "substeps": [],
                }
            )
        if selected is None:
            metrics[2] = {"label": "Selection", "value": "none", "note": "Explicit abstention", "tone": "danger"}
    steps.append(
        _human_step("Credit acceptance, a payment plan or any outbound reply needs a person. Nothing is sent or charged.")
    )
    outcome = {
        "credit_decision": decision,
        "overdue_total_rupees": str(overdue_total),
        "order_value_rupees": str(order_value),
        "exposure_rupees": str(exposure),
        "credit_limit_rupees": str(limit),
        "executes_credit_decision": False,
    }
    if decision_mode_applied:
        outcome["selected_option_id"] = selected["option_id"] if selected else None
        outcome["decision_status"] = decision_record.get("status", "recommended")
    return _result(
        message, event, extraction, fixture, state, "credit_review", summary,
        metrics,
        sections, steps,
        [f"receivable:{row['receivable_id']}" for row in overdue],
        ["Exposure is a planning input; no credit limit is enforced or changed by the system.", "Expected future collections are not counted."],
        [f"Credit decision: {decision.replace('_', ' ')}. This is a review flag, not a credit decision."],
        outcome=outcome,
        options=options,
        decision=decision_record,
        decision_mode=decision_mode,
        decision_mode_applied=decision_mode_applied,
        review_status=review_status,
    )


def run_scheme_claim(
    message: MessageSubmission,
    event: BusinessEvent,
    extraction: Extraction,
    state: BusinessState,
    fixture: ScenarioFixture | None,
    tables: dict[str, list[dict]],
    decision_mode: str = "deterministic",
) -> dict:
    subject = _subject(fixture, extraction, "scheme_id", "retailer_id", "sku_id", "invoice_reference")
    scheme = _find(tables["schemes"], "scheme_id", subject.get("scheme_id"))
    claimed_discount = Decimal(str((fixture.subject.get("claimed_discount_percent") if fixture else 0) or 0))
    claimed_units = int((fixture.subject.get("claimed_quantity_units") if fixture else 0) or 0)
    if not claimed_units and extraction.fact("quantity") is not None:
        claimed_units = int(extraction.fact("quantity").value)
    as_of = state.as_of.date()
    checks = []
    if scheme is None:
        checks.append(("scheme exists", False, "No approved scheme matches the reference."))
        approved_discount = Decimal("0")
        min_units = 0
    else:
        approved_discount = Decimal(scheme["discount_percent"])
        min_units = int(scheme["min_quantity_units"])
        valid_from, valid_to = date.fromisoformat(scheme["valid_from"]), date.fromisoformat(scheme["valid_to"])
        checks = [
            ("scheme approved", scheme["status"] == "approved", scheme["status"]),
            ("in validity window", valid_from <= as_of <= valid_to, f"{scheme['valid_from']} to {scheme['valid_to']}"),
            ("minimum quantity met", claimed_units >= min_units, f"claimed {claimed_units}, minimum {min_units}"),
            ("discount matches", claimed_discount == approved_discount, f"claimed {claimed_discount}%, approved {approved_discount}%"),
        ]
    mismatch = [label for label, passed, _ in checks if not passed]
    if scheme is None:
        status = "no_scheme_match"
    elif mismatch:
        status = "claim_mismatch"
    else:
        status = "claim_supported"
    approved_label = f"{approved_discount}%" if scheme else "none"
    summary = (
        f"Claim for {subject.get('scheme_id') or 'no scheme reference'}: {claimed_discount}% off "
        f"{claimed_units} units. The approved scheme gives {approved_label} with a minimum of "
        f"{min_units} units. "
        + ("The claim matches the register and still needs human approval before any credit note." if status == "claim_supported"
           else "The claim does not match the scheme register; no discount or credit note is applied.")
    )
    sections = [
        {
            "title": "Approved scheme terms",
            "description": "The scheme register is the only source of approved promotion terms.",
            "rows": [
                {"Field": "Scheme", "Value": scheme["scheme_id"] if scheme else "not found"},
                {"Field": "Name", "Value": scheme["scheme_name"] if scheme else "—"},
                {"Field": "SKU", "Value": scheme["sku_id"] if scheme else "—"},
                {"Field": "Discount", "Value": approved_label},
                {"Field": "Minimum quantity", "Value": f"{min_units} units"},
                {"Field": "Validity", "Value": f"{scheme['valid_from']} to {scheme['valid_to']}" if scheme else "—"},
            ],
        },
        {
            "title": "Claim checks",
            "description": "Each check compares the retailer's claim with the approved terms at the decision date.",
            "rows": [
                {"Check": label, "Result": "passed" if passed else "failed", "Detail": detail}
                for label, passed, detail in checks
            ],
        },
    ]
    steps = _opening_steps(message, event, extraction) + [
        {
            "title": "Scheme register checked",
            "detail": f"{len(checks)} checks compared the claim with the approved terms. {len(mismatch)} failed.",
            "status": "done",
            "substeps": [f"{label}: {detail}" for label, passed, detail in checks],
        },
        _human_step("A credit note, replacement or reply changes money or commitments, so a person must decide it."),
    ]
    return _result(
        message, event, extraction, fixture, state, "scheme_claim_review", summary,
        [
            {"label": "Claimed", "value": f"{claimed_discount}%", "note": f"{claimed_units} units", "tone": "warning"},
            {"label": "Approved", "value": approved_label, "note": f"Minimum {min_units} units", "tone": "accent"},
            {"label": "Checks failed", "value": str(len(mismatch)), "note": "At the decision date", "tone": "danger" if mismatch else "success"},
        ],
        sections, steps, [f"scheme:{scheme['scheme_id']}"] if scheme else [],
        ["Scheme terms are read from the versioned register.", "No invoice is changed by this review."],
        [f"Scheme claim status: {status.replace('_', ' ')}."],
        outcome={
            "claim_status": status,
            "claimed_discount_percent": int(claimed_discount) if claimed_discount == int(claimed_discount) else float(claimed_discount),
            "approved_discount_percent": str(approved_discount),
            "minimum_quantity_units": min_units,
            "executes_discount": False,
        },
        decision_mode=decision_mode,
    )


def run_delivery_discrepancy(
    message: MessageSubmission,
    event: BusinessEvent,
    extraction: Extraction,
    state: BusinessState,
    fixture: ScenarioFixture | None,
    tables: dict[str, list[dict]],
    decision_mode: str = "deterministic",
) -> dict:
    subject = _subject(fixture, extraction, "delivery_id", "retailer_id", "invoice_reference")
    evidence = _find(tables["delivery_evidence"], "delivery_id", subject.get("delivery_id"))
    if evidence is None:
        evidence = _find(tables["delivery_evidence"], "invoice_reference", subject.get("invoice_reference"))
    if evidence is None:
        summary = "No delivery record matches this report, so a person must locate the purchase order and proof of delivery."
        rows = [{"Record": "Delivery", "Value": "not found"}]
        return _result(
            message, event, extraction, fixture, state, "delivery_discrepancy_review", summary,
            [{"label": "Delivery", "value": "not found", "note": "Manual lookup required", "tone": "warning"}],
            [{"title": "Delivery evidence", "description": "No matching record.", "rows": rows}],
            _opening_steps(message, event, extraction) + [_human_step("Locate the order and POD before any claim.")],
            [], ["Reported details are unverified until matched to dispatch evidence."],
            ["Delivery record not found."],
            decision_mode=decision_mode,
        )
    ordered = int(evidence["ordered_units"])
    received = int(evidence["received_units"])
    damaged = int(evidence["damaged_units"])
    wrong = int(evidence["wrong_item_units"])
    short = max(ordered - received, 0)
    usable = max(received - damaged - wrong, 0)
    net_short = max(ordered - usable, 0)
    unit = evidence["unit"]
    summary = (
        f"Delivery {evidence['delivery_id']} ordered {format_units(ordered, unit)}. "
        f"{format_units(received, unit)} arrived, with {damaged} damaged and {wrong} wrong-item. "
        f"Usable quantity is {format_units(usable, unit)}, a net shortfall of {format_units(net_short, unit)}. "
        "Raise a supplier claim for human approval."
    )
    sections = [
        {
            "title": "Delivery reconciliation",
            "description": "Received, damaged and wrong-item counts come from the delivery evidence record.",
            "rows": [
                {"Item": "Ordered", "Units": ordered},
                {"Item": "Received", "Units": received},
                {"Item": "Damaged", "Units": damaged},
                {"Item": "Wrong item", "Units": wrong},
                {"Item": "Usable", "Units": usable},
                {"Item": "Net shortfall", "Units": net_short},
            ],
        },
        {
            "title": "Source record",
            "description": "Invoice and proof-of-delivery references keep the claim auditable.",
            "rows": [
                {"Field": "Retailer", "Value": evidence["retailer_id"]},
                {"Field": "SKU", "Value": evidence["sku_id"]},
                {"Field": "Invoice", "Value": evidence["invoice_reference"]},
                {"Field": "Proof of delivery", "Value": evidence["pod_reference"]},
                {"Field": "Checked on", "Value": evidence["checked_on"]},
                {"Field": "Record status", "Value": evidence["status"]},
            ],
        },
    ]
    steps = _opening_steps(message, event, extraction) + [
        {
            "title": "Delivery evidence checked",
            "detail": f"The order line, receipt, damage and wrong-item counts reconcile to a net shortfall of {format_units(net_short, unit)}.",
            "status": "done",
            "substeps": [],
        },
        _human_step("A credit note, replacement or retailer reply needs approval. Stock is not adjusted by this review."),
    ]
    return _result(
        message, event, extraction, fixture, state, "delivery_discrepancy_review", summary,
        [
            {"label": "Net shortfall", "value": format_units(net_short, unit), "note": "After damage and wrong items", "tone": "danger" if net_short else "success"},
            {"label": "Damaged", "value": str(damaged), "note": unit, "tone": "warning"},
            {"label": "Wrong item", "value": str(wrong), "note": unit, "tone": "warning"},
        ],
        sections, steps,
        [f"delivery:{evidence['delivery_id']}", f"invoice:{evidence['invoice_reference']}"],
        ["The claim value is not calculated; the supplier's short-delivery clause and rate must be checked by a person."],
        [f"Supplier claim candidate: {format_units(net_short, unit)}." if net_short else "No net shortfall found."],
        outcome={
            "ordered_units": ordered,
            "received_units": received,
            "damaged_units": damaged,
            "wrong_item_units": wrong,
            "usable_units": usable,
            "net_shortfall_units": net_short,
            "executes_claim": False,
        },
        decision_mode=decision_mode,
    )


def run_batch_recall(
    message: MessageSubmission,
    event: BusinessEvent,
    extraction: Extraction,
    state: BusinessState,
    fixture: ScenarioFixture | None,
    tables: dict[str, list[dict]],
    decision_mode: str = "deterministic",
) -> dict:
    subject = _subject(fixture, extraction, "recall_id", "batch_id")
    recall = _find(tables["recalls"], "recall_id", subject.get("recall_id"))
    batch = _find(tables["batches"], "batch_id", subject.get("batch_id"))
    if recall is not None and batch is None:
        batch = _find(tables["batches"], "batch_id", recall["batch_id"])
    if batch is None:
        summary = "No batch record matches this recall notice; a person must identify the affected stock."
        return _result(
            message, event, extraction, fixture, state, "recall_review", summary,
            [{"label": "Batch", "value": "not found", "note": "Manual lookup required", "tone": "warning"}],
            [{"title": "Recall notice", "description": "No matching batch.", "rows": [{"Recall": subject.get('recall_id') or 'not found'}]}],
            _opening_steps(message, event, extraction) + [_human_step("Identify the batch and quarantine it manually.")],
            [], ["A recall notice is a reported instruction until verified."], ["Batch record not found."],
            decision_mode=decision_mode,
        )
    inventory = _find(state.inventory, "sku_id", batch["sku_id"])
    on_hand = int(inventory["on_hand_units"]) if inventory else 0
    reserved = int(inventory["reserved_units"]) if inventory else 0
    quarantine = min(int(batch["quantity_units"]), max(on_hand - reserved, 0)) if inventory else 0
    affected = [row for row in state.open_orders if row["sku_id"] == batch["sku_id"]]
    recall_ref = recall["recall_id"] if recall else subject.get("recall_id")
    options = [
        _review_option(
            "opt-quarantine-batch",
            f"Quarantine batch {batch['batch_id']}",
            (
                f"Hold {quarantine} unreserved {batch['unit']} of {batch['sku_id']}; {len(affected)} open "
                "order(s) keep their current status pending a person."
            ),
            0,
            f"Keeps the affected stock out of allocation as {recall_ref} requires.",
        )
    ]
    infeasible = [
        _review_option(
            "opt-release-batch",
            f"Release batch {batch['batch_id']}",
            f"Leave {batch['quantity_units']} {batch['unit']} available for allocation and dispatch.",
            1,
            f"{recall_ref} requires the batch held; releasing it would ship affected stock.",
            feasible=False,
        )
    ]
    decision_mode_applied = True
    selected: dict | None = options[0]
    review_status = "pending_review"
    if decision_mode == "policy_grounded_llm":
        selected, decision_record, _ = _grounded_review_decision(
            event, state, options, infeasible, "POL-STK-007", "recall review outcome"
        )
    else:
        decision_record = {
            "mode": "deterministic",
            "status": "recommended",
            "option_id": selected["option_id"],
            "priority": "policy_requirement",
            "rationale": (
                "Fixed rule: a batch named in a recall notice is not released to allocation. Quarantine keeps "
                "the affected stock out of fulfilment until a person approves; releasing the batch is infeasible. "
                "Policy passages are reference material and did not change this rule."
            ),
            "tradeoff": _review_tradeoff(options, infeasible, selected["option_id"]),
            "citations": [],
            "retrieved_policies": [],
        }
    base = (
        f"Recall {recall_ref} covers batch {batch['batch_id']} "
        f"({batch['quantity_units']} {batch['unit']}, {batch['sku_id']}). "
        f"Up to {quarantine} units are currently free to hold; {len(affected)} open order(s) use this SKU. "
    )
    if selected is None:
        reason = decision_record.get("abstain_reason") or "No verified outcome was selected."
        summary = (
            base
            + f"Policy-grounded mode did not select a review outcome: {reason} "
            "A person must decide; nothing is held or shipped."
        )
        review_status = "needs_clarification"
    else:
        if decision_mode == "deterministic":
            selection_note = (
                f"A fixed rule selected: {selected['label']}. No model was called and no policy passage was read "
                "for the choice."
            )
        else:
            cited = ", ".join(decision_record.get("citations") or []) or "no document"
            selection_note = (
                f"The model confirmed: {selected['label']}, citing {cited}. The app checked the choice against the "
                "supplied options and citations."
            )
        summary = base + selection_note + " A person must approve quarantine, substitution or retailer communication."
    sections = [
        {
            "title": "Recall notice",
            "description": "The notice is shown as reported, with its authority and required action.",
            "rows": [
                {"Field": "Recall", "Value": recall["recall_id"] if recall else subject.get("recall_id")},
                {"Field": "Reason", "Value": recall["reason"] if recall else "not recorded"},
                {"Field": "Authority", "Value": recall["authority"] if recall else "not recorded"},
                {"Field": "Issued on", "Value": recall["issued_on"] if recall else "not recorded"},
                {"Field": "Required action", "Value": recall["required_action"] if recall else "not recorded"},
            ],
        },
        {
            "title": "Affected stock",
            "description": "Quarantine is limited to unreserved stock currently on hand.",
            "rows": [
                {"Item": "Batch", "Value": batch["batch_id"]},
                {"Item": "SKU", "Value": batch["sku_id"]},
                {"Item": "Expiry", "Value": batch["expiry_date"]},
                {"Item": "On hand", "Value": on_hand},
                {"Item": "Reserved", "Value": reserved},
                {"Item": "Free to quarantine", "Value": quarantine},
            ],
        },
        {
            "title": "Open orders using this SKU",
            "description": "These orders are not changed; a person decides substitution or delay.",
            "rows": [
                {"Order": row["order_id"], "Retailer": row["retailer_id"], "Quantity": row["quantity_units"], "Promised": row["requested_delivery_date"]}
                for row in affected
            ] or [{"Order": "None", "Retailer": "—", "Quantity": 0, "Promised": "—"}],
        },
    ]
    sections.append(
        _review_options_section(
            options,
            infeasible,
            selected["option_id"] if selected else None,
            (
                "A recalled batch has one feasible review outcome. Releasing the batch is shown with the reason "
                "it cannot be selected; no option moves or destroys stock."
            ),
        )
    )
    sections.append(_review_decision_section(decision_record, options))
    steps = _opening_steps(message, event, extraction) + [
        {
            "title": "Batch and orders checked",
            "detail": f"{quarantine} unreserved units can be held; {len(affected)} open orders use {batch['sku_id']}.",
            "status": "done",
            "substeps": [],
        },
        {
            "title": "Options compared",
            "detail": (
                f"{len(options)} feasible review outcome(s) and {len(infeasible)} infeasible option(s) were compared."
                if selected
                else f"{len(options)} feasible review outcome(s) were compared; none was selected."
            ),
            "status": "done",
            "substeps": [
                f"{option['label']} — "
                + _review_verdict(option, selected["option_id"] if selected else None)
                for option in [*options, *infeasible]
            ],
        },
    ]
    if selected:
        steps.append(
            {
                "title": "Policy-grounded check" if decision_mode == "policy_grounded_llm" else "Fixed rule applied",
                "detail": (
                    f"The model confirmed {selected['label']} citing "
                    f"{', '.join(decision_record.get('citations') or [])}."
                    if decision_mode == "policy_grounded_llm"
                    else "The fixed recall rule selected the outcome; policy passages are reference material."
                ),
                "status": "done",
                "substeps": [],
            }
        )
    else:
        steps.append(
            {
                "title": "Selection stopped",
                "detail": (
                    "No review outcome was selected: "
                    f"{decision_record.get('abstain_reason') or 'No verified outcome was selected.'}"
                ),
                "status": "blocked",
                "substeps": [],
            }
        )
    steps.append(
        _human_step("Quarantine, substitution and retailer communication need approval. No stock is moved here.")
    )
    metrics = [
        {"label": "Free to hold", "value": str(quarantine), "note": batch["unit"], "tone": "danger"},
        {"label": "Open orders", "value": str(len(affected)), "note": "Use this SKU", "tone": "warning"},
        {"label": "Batch status", "value": batch["status"].replace("_", " "), "note": batch["batch_id"], "tone": "warning"},
    ]
    if selected is None:
        metrics[2] = {"label": "Selection", "value": "none", "note": "Explicit abstention", "tone": "danger"}
    return _result(
        message, event, extraction, fixture, state, "recall_review", summary,
        metrics,
        sections, steps, [f"batch:{batch['batch_id']}"] + ([f"recall:{recall['recall_id']}"] if recall else []),
        ["The recall notice is treated as reported; a person must verify scope before disposal or substitution."],
        ["Quality hold recommended for the affected batch."],
        outcome={
            "batch_id": batch["batch_id"],
            "free_to_quarantine_units": quarantine,
            "affected_open_orders": len(affected),
            "selected_option_id": selected["option_id"] if selected else None,
            "decision_status": decision_record.get("status", "recommended"),
            "executes_quarantine": False,
        },
        options=options,
        decision=decision_record,
        decision_mode=decision_mode,
        decision_mode_applied=decision_mode_applied,
        review_status=review_status,
    )


def run_short_dated_stock(
    message: MessageSubmission,
    event: BusinessEvent,
    extraction: Extraction,
    state: BusinessState,
    fixture: ScenarioFixture | None,
    tables: dict[str, list[dict]],
    decision_mode: str = "deterministic",
) -> dict:
    subject = _subject(fixture, extraction, "batch_id")
    batch = _find(tables["batches"], "batch_id", subject.get("batch_id"))
    if batch is None:
        summary = "No batch record matches this report; a person must check expiry dates manually."
        return _result(
            message, event, extraction, fixture, state, "expiry_review", summary,
            [{"label": "Batch", "value": "not found", "note": "Manual lookup required", "tone": "warning"}],
            [{"title": "Batch", "description": "No matching record.", "rows": [{"Batch": subject.get('batch_id') or 'not found'}]}],
            _opening_steps(message, event, extraction) + [_human_step("Check expiry and return terms manually.")],
            [], ["Expiry dates are unavailable for this batch."], ["Batch record not found."],
            decision_mode=decision_mode,
        )
    expiry = date.fromisoformat(batch["expiry_date"])
    days_left = (expiry - state.as_of.date()).days
    window = int(batch["supplier_return_window_days"])
    eligible = days_left <= window
    orders = [row for row in state.open_orders if row["sku_id"] == batch["sku_id"]]
    requested = sum(int(row["quantity_units"]) for row in orders)
    summary = (
        f"Batch {batch['batch_id']} ({batch['quantity_units']} {batch['unit']} of {batch['sku_id']}) expires on "
        f"{batch['expiry_date']}, {days_left} days from the decision date. The supplier return window is {window} days, "
        + ("so the batch is inside the return window. Recommend a return or priority dispatch for human approval."
           if eligible else "so the batch is outside the return window. Recommend priority dispatch and closer monitoring.")
    )
    sections = [
        {
            "title": "Batch position",
            "description": "Days remaining and return eligibility are calculated from the versioned batch record.",
            "rows": [
                {"Item": "Batch", "Value": batch["batch_id"]},
                {"Item": "SKU", "Value": batch["sku_id"]},
                {"Item": "Quantity", "Value": f"{batch['quantity_units']} {batch['unit']}"},
                {"Item": "Expiry", "Value": batch["expiry_date"]},
                {"Item": "Days to expiry", "Value": days_left},
                {"Item": "Supplier return window", "Value": f"{window} days"},
                {"Item": "Return eligible", "Value": "Yes" if eligible else "No"},
            ],
        },
        {
            "title": "Open demand for this SKU",
            "description": "Priority dispatch is an option only after a person checks these orders.",
            "rows": [
                {"Order": row["order_id"], "Retailer": row["retailer_id"], "Quantity": row["quantity_units"], "Promised": row["requested_delivery_date"]}
                for row in orders
            ] or [{"Order": "None", "Retailer": "—", "Quantity": 0, "Promised": "—"}],
        },
    ]
    steps = _opening_steps(message, event, extraction) + [
        {
            "title": "Expiry and return terms checked",
            "detail": f"{days_left} days remain against a {window}-day supplier return window; {requested} units are on open orders.",
            "status": "done",
            "substeps": [],
        },
        _human_step("A return, markdown or dispatch priority change needs approval. No stock or price is changed here."),
    ]
    return _result(
        message, event, extraction, fixture, state, "expiry_review", summary,
        [
            {"label": "Days to expiry", "value": str(days_left), "note": batch["expiry_date"], "tone": "danger" if days_left <= window else "warning"},
            {"label": "Return window", "value": f"{window} days", "note": "Supplier terms", "tone": "accent"},
            {"label": "Open demand", "value": str(requested), "note": batch["unit"], "tone": "warning"},
        ],
        sections, steps, [f"batch:{batch['batch_id']}"],
        ["Expiry and return-window values come from the batch record and supplier terms.", "No goods are moved, returned or discounted by this review."],
        ["Short-dated stock flagged for human decision."],
        outcome={
            "batch_id": batch["batch_id"],
            "days_to_expiry": days_left,
            "supplier_return_window_days": window,
            "return_eligible": eligible,
            "executes_return": False,
        },
        decision_mode=decision_mode,
    )


DISPATCH_PRIORITY_RANK = {"high": 0, "normal": 1, "low": 2}


def _dispatch_option_key(option: dict) -> tuple:
    return (
        option["deferred_high_priority"],
        option["promise_breaches"],
        option["deferred_orders"],
        option["deferred_units"],
        -option["loaded_units"],
        option["option_id"],
    )


def _dispatch_option(
    loaded: list[dict], deferred: list[dict], capacity: int, departure_date: str
) -> dict:
    loaded_units = sum(int(row["quantity_units"]) for row in loaded)
    deferred_units = sum(int(row["quantity_units"]) for row in deferred)
    return {
        "option_id": "opt-" + ("+".join(sorted(row["order_id"] for row in loaded)) or "none"),
        "label": (
            "Load " + ", ".join(row["order_id"] for row in sorted(loaded, key=lambda row: row["order_id"]))
            if loaded else "Load no orders"
        ),
        "loaded_order_ids": [row["order_id"] for row in sorted(loaded, key=lambda row: row["order_id"])],
        "deferred_order_ids": [row["order_id"] for row in sorted(deferred, key=lambda row: row["order_id"])],
        "loaded_units": loaded_units,
        "deferred_units": deferred_units,
        "deferred_orders": len(deferred),
        "deferred_high_priority": sum(1 for row in deferred if row["priority"] == "high"),
        "promise_breaches": sum(1 for row in deferred if row["promised_date"] <= departure_date),
        "utilisation_percent": round(loaded_units / capacity * 100, 1) if capacity else 0.0,
    }


def _dispatch_options(
    orders: list[dict], capacity: int, departure_date: str
) -> tuple[list[dict], list[dict]]:
    """Every non-split load plan that fits, plus the over-capacity all-orders option."""
    feasible: list[dict] = []
    for mask in range(1 << len(orders)):
        loaded = [row for index, row in enumerate(orders) if mask & (1 << index)]
        if sum(int(row["quantity_units"]) for row in loaded) > capacity:
            continue
        deferred = [row for row in orders if row not in loaded]
        feasible.append(_dispatch_option(loaded, deferred, capacity, departure_date))
    feasible.sort(key=_dispatch_option_key)

    demand = sum(int(row["quantity_units"]) for row in orders)
    infeasible = []
    if demand > capacity:
        infeasible.append(
            {
                "option_id": "opt-all",
                "label": f"Load all {len(orders)} orders",
                "loaded_units": demand,
                "deferred_units": 0,
                "deferred_orders": 0,
                "promise_breaches": 0,
                "feasible": False,
                "reason": f"Exceeds capacity by {demand - capacity} units",
            }
        )
    return feasible, infeasible


def _dispatch_verdict(option: dict, selected: dict) -> str:
    if option["option_id"] == selected["option_id"]:
        return "Selected"
    reasons = []
    if option["deferred_high_priority"] > selected["deferred_high_priority"]:
        reasons.append("defers a high-priority order")
    if option["promise_breaches"] > selected["promise_breaches"]:
        reasons.append(
            f"defers {option['promise_breaches'] - selected['promise_breaches']} more order(s) promised by departure"
        )
    if option["deferred_orders"] > selected["deferred_orders"]:
        reasons.append(f"defers {option['deferred_orders'] - selected['deferred_orders']} more order(s)")
    if option["deferred_units"] > selected["deferred_units"]:
        reasons.append(f"leaves {option['deferred_units'] - selected['deferred_units']} more units unshipped")
    if option["loaded_units"] < selected["loaded_units"]:
        reasons.append(f"loads {selected['loaded_units'] - option['loaded_units']} fewer units")
    if not reasons:
        return "Same service result; the fixed tie-break keeps the selected option"
    return "Rejected: " + "; ".join(reasons)


def _dispatch_options_section(feasible: list[dict], infeasible: list[dict], capacity: int) -> dict:
    rows = [
        {
            "Option": option["label"],
            "Loaded": f"{option['loaded_units']}/{capacity}",
            "Deferred": option["deferred_orders"],
            "Deferred units": option["deferred_units"],
            "Promises at risk": option["promise_breaches"],
            "Result": _dispatch_verdict(option, feasible[0]),
        }
        for option in feasible
    ]
    rows.extend(
        {
            "Option": option["label"],
            "Loaded": f"{option['loaded_units']}/{capacity}",
            "Deferred": "—",
            "Deferred units": "—",
            "Promises at risk": "—",
            "Result": f"Infeasible: {option['reason']}",
        }
        for option in infeasible
    )
    return {
        "title": "Options considered",
        "description": (
            "Every non-split load plan that fits the vehicle is compared. High priority first, then the earliest "
            "promised date, then the number of deferred orders and units."
        ),
        "rows": rows,
    }


def _dispatch_tradeoff(selected: dict, feasible: list[dict]) -> str:
    others = [option for option in feasible if option["option_id"] != selected["option_id"]]
    if not others:
        return "No other feasible option was available."
    alternative = min(others, key=lambda option: _dispatch_option_key(option)[:-1])
    return (
        f"Next-best {alternative['label']}: {alternative['loaded_units']} units loaded, "
        f"{alternative['deferred_orders']} order(s) deferred and "
        f"{alternative['promise_breaches']} promise breach(es)."
    )


def _dispatch_decision_section(decision: dict, feasible: list[dict]) -> dict:
    mode = str(decision.get("mode") or "deterministic").replace("_", " ").title()
    status = str(decision.get("status") or "recommended").replace("_", " ")
    citations = ", ".join(decision.get("citations") or []) or "none"
    rows = [
        {"Field": "Mode", "Value": mode},
        {"Field": "Decided by", "Value": _decided_by(decision)},
        {"Field": "Role of the policies", "Value": _policy_role(decision)},
        {"Field": "Status", "Value": status},
        {"Field": "Selected option", "Value": decision.get("option_id") or "none"},
        {"Field": "Stated priority", "Value": (decision.get("priority") or "—").replace("_", " ")},
        {"Field": "Cited policies", "Value": citations},
        {"Field": "Rationale", "Value": decision.get("rationale") or "—"},
        {"Field": "Next-best option", "Value": decision.get("tradeoff") or "—"},
    ]
    if decision.get("mode") == "policy_grounded_llm":
        description = (
            "The model confirmed one of the supplied load plans or abstained. It cannot invent plans, numbers or "
            "waive the vehicle capacity limit; the app checked its citations and arithmetic."
        )
    else:
        description = (
            "A fixed rule picked the load plan. No model was called and no policy passage was read; the policies "
            "shown elsewhere are for the reviewer's reference only."
        )
    return {"title": "Decision rationale", "description": description, "rows": rows}


def run_dispatch_planning(
    message: MessageSubmission,
    event: BusinessEvent,
    extraction: Extraction,
    state: BusinessState,
    fixture: ScenarioFixture | None,
    tables: dict[str, list[dict]],
    decision_mode: str = "deterministic",
) -> dict:
    subject = _subject(fixture, extraction, "route_id")
    route = _find(tables["routes"], "route_id", subject.get("route_id"))
    if route is None:
        summary = "No route record matches this report; a person must build the load plan manually."
        return _result(
            message, event, extraction, fixture, state, "dispatch_review", summary,
            [{"label": "Route", "value": "not found", "note": "Manual lookup required", "tone": "warning"}],
            [{"title": "Route", "description": "No matching record.", "rows": [{"Route": subject.get('route_id') or 'not found'}]}],
            _opening_steps(message, event, extraction) + [_human_step("Build and check the load plan manually.")],
            [], ["Vehicle capacity is not on record."], ["Route record not found."],
            decision_mode=decision_mode,
        )
    orders = [row for row in tables["dispatch_orders"] if row["route_id"] == route["route_id"]]
    capacity = int(route["capacity_units"])
    demand = sum(int(row["quantity_units"]) for row in orders)
    feasible, infeasible = _dispatch_options(orders, capacity, route["departure_date"])
    best = feasible[0]
    selected = best
    decision_mode_applied = True
    references: list[dict] = []

    if decision_mode == "policy_grounded_llm":
        try:
            context = policy_context(event.event_type, None, state.as_of.date())
            references = context["passages"]
            selected_id, decision = recommend_advisory_option(
                event.model_dump(mode="json"), feasible, references, capacity, demand, infeasible
            )
        except Exception as exc:
            selected_id, decision = None, {
                "mode": "policy_grounded_llm",
                "status": "abstained",
                "option_id": None,
                "priority": None,
                "rationale": "Policy retrieval failed; no option was selected.",
                "tradeoff": "",
                "citations": [],
                "retrieved_policies": [],
                "abstain_reason": f"Policy retrieval failed: {type(exc).__name__}",
            }
        selected = next((option for option in feasible if option["option_id"] == selected_id), None)
    else:
        decision = {
            "mode": "deterministic",
            "status": "recommended",
            "option_id": best["option_id"],
            "priority": "service",
            "rationale": (
                "Fixed service ranking: high-priority deferrals, then promise breaches, then deferred orders, "
                "then deferred units, then the largest load. Policy passages are reference material and did not "
                "change this ranking."
            ),
            "tradeoff": _dispatch_tradeoff(best, feasible),
            "citations": [],
            "retrieved_policies": [],
        }

    abstained = selected is None
    if abstained:
        reason = decision.get("abstain_reason") or "No verified option was selected."
        summary = (
            f"Route {route['route_id']} ({route['vehicle_label']}) has {capacity} units of capacity and "
            f"{demand} units of demand across {len(orders)} order(s). Policy-grounded mode did not select a plan: "
            f"{reason} A person must decide; nothing is dispatched."
        )
        metrics = [
            {"label": "Capacity", "value": f"{capacity} units", "note": route["vehicle_label"], "tone": "accent"},
            {"label": "Demand", "value": f"{demand} units", "note": f"{len(orders)} orders", "tone": "warning"},
            {"label": "Selection", "value": "none", "note": "Explicit abstention", "tone": "danger"},
        ]
        sections = [
            {
                "title": "Vehicle and route",
                "description": "Capacity is a hard constraint; orders are not split across vehicles here.",
                "rows": [
                    {"Field": "Route", "Value": route["route_id"]},
                    {"Field": "Vehicle", "Value": route["vehicle_label"]},
                    {"Field": "Area", "Value": route["area"]},
                    {"Field": "Departure", "Value": route["departure_date"]},
                    {"Field": "Capacity", "Value": f"{capacity} units"},
                    {"Field": "Demand", "Value": f"{demand} units"},
                ],
            },
            _dispatch_options_section(feasible, infeasible, capacity),
            _dispatch_decision_section(decision, feasible),
        ]
        steps = _opening_steps(message, event, extraction) + [
            {
                "title": "Options compared",
                "detail": (
                    f"{len(feasible)} feasible load plans were compared; none ships all {demand} units. "
                    "The model was asked to confirm one option or abstain."
                ),
                "status": "done",
                "substeps": [],
            },
            {
                "title": "Selection stopped",
                "detail": f"No option was selected: {reason}",
                "status": "blocked",
                "substeps": [],
            },
            _human_step("A person must choose a load plan, reschedule or split the deferred order. Nothing is dispatched here."),
        ]
        return _result(
            message, event, extraction, fixture, state, "dispatch_review", summary,
            metrics, sections, steps, [f"route:{route['route_id']}"],
            ["Capacity and order assignments come from the route record.", "No dispatch instruction or message is sent by this review."],
            ["No policy-grounded option was selected."],
            outcome={
                "route_id": route["route_id"],
                "capacity_units": capacity,
                "demand_units": demand,
                "deferred_orders": best["deferred_orders"],
                "selected_option_id": None,
                "decision_status": "abstained",
                "executes_dispatch": False,
            },
            options=feasible,
            decision=decision,
            decision_mode=decision_mode,
            decision_mode_applied=decision_mode_applied,
            review_status="needs_clarification",
        )

    used = selected["loaded_units"]
    summary = (
        f"Route {route['route_id']} ({route['vehicle_label']}) has {capacity} units of capacity and "
        f"{demand} units of demand across {len(orders)} order(s). "
        f"{'Deterministic ranking' if decision_mode == 'deterministic' else 'Policy-grounded mode'} selected "
        f"{selected['label']}: {used} units load and {selected['deferred_orders']} order(s) defer. "
        f"This is the best of {len(feasible)} feasible load plans; no plan ships all {demand} units. "
        "The load plan needs human approval before dispatch."
    )
    load_rows = [
        {
            "Order": row["order_id"],
            "Retailer": row["retailer_id"],
            "Quantity": row["quantity_units"],
            "Priority": row["priority"],
            "Promised": row["promised_date"],
            "Load": "loaded" if row["order_id"] in selected["loaded_order_ids"] else "deferred",
        }
        for row in sorted(
            orders,
            key=lambda row: (
                row["order_id"] not in selected["loaded_order_ids"],
                DISPATCH_PRIORITY_RANK.get(row["priority"], 9),
                row["promised_date"],
                row["order_id"],
            ),
        )
    ]
    sections = [
        {
            "title": "Vehicle and route",
            "description": "Capacity is a hard constraint; orders are not split across vehicles here.",
            "rows": [
                {"Field": "Route", "Value": route["route_id"]},
                {"Field": "Vehicle", "Value": route["vehicle_label"]},
                {"Field": "Area", "Value": route["area"]},
                {"Field": "Departure", "Value": route["departure_date"]},
                {"Field": "Capacity", "Value": f"{capacity} units"},
                {"Field": "Loaded", "Value": f"{used} units"},
                {"Field": "Utilisation", "Value": f"{selected['utilisation_percent']}%"},
            ],
        },
        {
            "title": "Load order",
            "description": "The selected option, sorted by load status, priority and promised date.",
            "rows": load_rows,
        },
        _dispatch_options_section(feasible, infeasible, capacity),
        _dispatch_decision_section(decision, feasible),
    ]
    steps = _opening_steps(message, event, extraction) + [
        {
            "title": "Capacity allocated",
            "detail": f"{used} of {capacity} units fit; {selected['deferred_orders']} order(s) do not.",
            "status": "done",
            "substeps": [],
        },
        {
            "title": "Options compared",
            "detail": (
                f"{len(feasible)} feasible load plans were compared; none ships all {demand} units. "
                "Each rejected option is shown with the reason it loses."
            ),
            "status": "done",
            "substeps": [
                f"{option['label']}: {option['loaded_units']} units loaded, "
                f"{option['deferred_orders']} deferred — {_dispatch_verdict(option, selected)}."
                for option in feasible[:4]
            ],
        },
        {
            "title": "Policy-grounded check" if decision_mode == "policy_grounded_llm" else "Fixed rule applied",
            "detail": (
                f"The model confirmed {selected['label']} citing "
                f"{', '.join(decision.get('citations') or [])}."
                if decision_mode == "policy_grounded_llm"
                else "The fixed service ranking selected the plan; policy passages are reference material."
            ),
            "status": "done",
            "substeps": [],
        },
        _human_step("Dispatching, splitting a load or rescheduling a deferred order needs approval. Nothing is dispatched here."),
    ]
    return _result(
        message, event, extraction, fixture, state, "dispatch_review", summary,
        [
            {"label": "Capacity used", "value": f"{used}/{capacity}", "note": "units", "tone": "accent"},
            {"label": "Deferred orders", "value": str(selected["deferred_orders"]), "note": "Beyond capacity", "tone": "danger" if selected["deferred_orders"] else "success"},
            {"label": "Departure", "value": route["departure_date"], "note": route["vehicle_label"], "tone": "warning"},
        ],
        sections, steps, [f"route:{route['route_id']}"],
        ["Capacity and order assignments come from the route record.", "No dispatch instruction or message is sent by this review."],
        ["Route capacity exceeded." if selected["deferred_orders"] else "All orders fit within capacity."],
        outcome={
            "route_id": route["route_id"],
            "capacity_units": capacity,
            "demand_units": demand,
            "deferred_orders": selected["deferred_orders"],
            "selected_option_id": selected["option_id"],
            "decision_status": decision.get("status", "recommended"),
            "executes_dispatch": False,
        },
        options=feasible,
        decision=decision,
        decision_mode=decision_mode,
        decision_mode_applied=decision_mode_applied,
    )


RUNNERS = {
    "credit_check": run_credit_check,
    "scheme_claim": run_scheme_claim,
    "delivery_discrepancy": run_delivery_discrepancy,
    "batch_recall": run_batch_recall,
    "short_dated_stock": run_short_dated_stock,
    "dispatch_planning": run_dispatch_planning,
}


def run_advisory_scenario(
    message: MessageSubmission,
    event: BusinessEvent,
    extraction: Extraction,
    state: BusinessState,
    fixture: ScenarioFixture | None = None,
    data_dir=None,
    decision_mode: str = "deterministic",
) -> dict:
    runner = RUNNERS.get(event.event_type)
    if runner is None:
        raise ValueError(f"No advisory review is defined for {event.event_type}")
    return runner(
        message, event, extraction, state, fixture, load_advisory_tables(data_dir), decision_mode
    )
