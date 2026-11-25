"""Shared rendering for the human review workspace. Pure presentation, no decision logic."""

from datetime import date
from decimal import Decimal
from html import escape

import streamlit as st

from app.dashboard.theme import badge, format_rupees, quote_html, section_title
from app.units import format_units, unit_word

RANKING_RULE = (
    "Fewest unfilled units first, then fewest late units, then earliest estimated arrival, then lowest cost. "
    "Policy passages are shown for context and do not change this ranking."
)

_RELATION_BADGES = {
    "cited": ("Cited by the LLM", "success"),
    "retrieved": ("Available to the LLM", "neutral"),
    "in_force": ("In force", "neutral"),
    "reference": ("Reference only", "neutral"),
}
ADVISORY_KINDS = {
    "credit_review",
    "scheme_claim_review",
    "delivery_discrepancy_review",
    "recall_review",
    "expiry_review",
    "dispatch_review",
}


def _money(value) -> str:
    return format_rupees(value)


def _units(value, unit: str) -> str:
    return format_units(value, unit)


def _steps(context: dict) -> list[dict]:
    steps = context.get("decision_steps") or []
    if steps:
        return steps
    alternatives = context.get("alternatives") or []
    selected = context.get("selected_candidate_id")
    return [
        {
            "title": "Message received",
            "detail": "This review record was saved before the detailed step trace was added.",
            "status": "done",
            "substeps": [],
        },
        {
            "title": "Options compared",
            "detail": f"{len(alternatives)} options were compared."
            + (f" The plan under review is {selected}." if selected else ""),
            "status": "done",
            "substeps": [],
        },
        {
            "title": "Waiting for a person",
            "detail": "Approval records the choice in the demo ledger only.",
            "status": "waiting",
            "substeps": [],
        },
    ]


def _summary(context: dict) -> str:
    summary = context.get("operator_summary")
    if summary:
        return summary
    if context.get("review_kind") == "operational_plan":
        return (
            f"The plan fulfils {context['selected_fulfilled_units']} of {context['requested_units']} "
            f"{context['unit']}, leaves {context['selected_unmet_units']} unfilled and "
            f"{context['selected_late_units']} arriving after the promised date, at a purchase cost of "
            f"{_money(context['selected_cost_rupees'])}."
        )
    return ""


def render_operator_summary(context: dict) -> None:
    summary = _summary(context)
    if not summary:
        return
    section_title("What this means", "The same facts, written the way an operator would say them")
    st.markdown(f'<div class="bb-summary">{escape(summary)}</div>', unsafe_allow_html=True)


def render_decision_steps(context: dict) -> None:
    steps = _steps(context)
    if not steps:
        return
    with st.container(border=True):
        section_title(
            "How the decision was reached",
            "The running system follows these steps in order every time, so the demo mirrors the real execution.",
        )
        blocks = []
        for index, step in enumerate(steps, start=1):
            status = step.get("status", "done")
            substeps = "".join(
                f"<li>{escape(str(line))}</li>" for line in step.get("substeps") or []
            )
            substeps_html = f'<ul class="bb-substeps">{substeps}</ul>' if substeps else ""
            blocks.append(
                f'<div class="bb-step bb-step-{escape(status)}">'
                f'<div class="bb-step-marker">{index}</div>'
                f'<div><div class="bb-step-title">{escape(step.get("title", ""))}</div>'
                f'<div class="bb-step-detail">{escape(step.get("detail", ""))}</div>'
                f"{substeps_html}</div></div>"
            )
        st.markdown(f'<div class="bb-steps">{"".join(blocks)}</div>', unsafe_allow_html=True)


def _trade_offs(context: dict) -> list[str]:
    selected = next((row for row in context["alternatives"] if row["selected"]), None)
    if selected is None:
        return []
    unit = context["unit"]
    selected_cost = Decimal(str(selected["total_cost_rupees"]))
    selected_arrival = context.get("selected_arrival_date")
    lines = []
    for alternative in context["alternatives"]:
        if alternative["selected"] or alternative["unmet_units"] != selected["unmet_units"]:
            continue
        extra_cost = selected_cost - Decimal(str(alternative["total_cost_rupees"]))
        if extra_cost <= 0:
            continue
        if alternative["late_units"] > selected["late_units"]:
            avoided = alternative["late_units"] - selected["late_units"]
            per_unit = (extra_cost / avoided).quantize(Decimal("0.01"))
            lines.append(
                (
                    extra_cost,
                    f"{_money(extra_cost)} more than {alternative['label']} avoids "
                    f"{_units(avoided, unit)} arriving late ({_money(per_unit)} per {unit_word(1, unit)}).",
                )
            )
        elif alternative["late_units"] == selected["late_units"] and selected_arrival and alternative["arrival_date"]:
            days = (date.fromisoformat(alternative["arrival_date"]) - date.fromisoformat(selected_arrival)).days
            if days > 0:
                day_word = "day" if days == 1 else "days"
                lines.append(
                    (
                        extra_cost,
                        f"{_money(extra_cost)} more than {alternative['label']} arrives {days} {day_word} earlier "
                        f"({selected_arrival} vs {alternative['arrival_date']}).",
                    )
                )
    return [text for _, text in sorted(lines)]


def render_decision(context: dict) -> None:
    unit = context["unit"]
    arrival = context.get("selected_arrival_date")
    section_title("Compare the options", "Every feasible option stays visible; excluded plans never enter the ranking.")
    st.write(
        f"{_units(context['requested_units'], unit)} are needed across {context['order_count']} open orders. "
        f"{_units(context['usable_units'], unit)} are free from stock now, so "
        f"{_units(context['required_units'], unit)} must be bought. The chosen plan fulfils "
        f"{context['selected_fulfilled_units']}, leaves {context['selected_unmet_units']} unfilled and "
        f"{context['selected_late_units']} arriving after the promised date"
        + (f" (estimated arrival {arrival})." if arrival else ".")
    )
    st.dataframe(
        [
            {
                "Option": row["label"] + (" · selected" if row["selected"] else ""),
                "Purchase cost": _money(row["total_cost_rupees"]),
                "Arrival (estimate)": row["arrival_date"] or "from stock now",
                "Arriving late": row["late_units"],
                "Unfilled": row["unmet_units"],
                "Cash left": _money(row["ending_cash_rupees"]),
                "Buffer left": _money(row["headroom_rupees"]),
            }
            for row in context["alternatives"]
        ],
        width="stretch",
        hide_index=True,
    )
    if context.get("decision_mode") == "policy_grounded_llm":
        decision = context.get("decision") or {}
        st.caption(
            "Selection: policy-grounded LLM · it chose from the checked options and cited the rules it relied on."
        )
        if decision.get("rationale"):
            st.info(decision["rationale"])
        if decision.get("tradeoff"):
            st.write(decision["tradeoff"])
    else:
        st.caption(f"Selection: fixed ranking rules · {RANKING_RULE}")
    exclusions = context.get("excluded_candidates") or []
    if exclusions:
        section_title("Options removed", "Each removal keeps its exact reason so the choice stays auditable.")
        st.dataframe(
            [
                {
                    "Option": row["candidate_id"],
                    "Supplier": row.get("supplier_id") or "—",
                    "Why it was removed": ", ".join(row["reasons"]),
                    "Details": "; ".join(f"{key}={value}" for key, value in row.get("details", {}).items()),
                }
                for row in exclusions
            ],
            width="stretch",
            hide_index=True,
        )
    for counterfactual in context.get("counterfactuals") or []:
        selected = counterfactual["selected_plan"]
        section_title(
            "What if supplier receipts arrived on time?",
            "Expected receipt dates replace actual dates only in this separate simulation; the real plan is unchanged.",
        )
        columns = st.columns(5)
        columns[0].metric("Option", selected["candidate_id"])
        columns[1].metric("Fulfilled", selected["fulfilled_units"])
        columns[2].metric("Late", selected["late_units"])
        columns[3].metric("Unfilled", selected["unmet_units"])
        columns[4].metric("Cost", _money(selected["total_cost_rupees"]))
        st.caption(
            f"Cash left {_money(selected['cash_projection']['ending_cash_rupees'])} · "
            f"{len(counterfactual.get('excluded_candidates') or [])} options removed · "
            f"independent check {'passed' if counterfactual['verification']['valid'] else 'failed'}"
        )
    if context.get("scenario_view") or context.get("cash_schedule"):
        with st.expander("Scenario settings and day-by-day cash"):
            if context.get("scenario_view"):
                st.json(context["scenario_view"])
            if context.get("cash_schedule"):
                st.dataframe(context["cash_schedule"], width="stretch", hide_index=True)
    trade_offs = _trade_offs(context)
    if trade_offs:
        section_title("What the extra money buys")
        for line in trade_offs:
            st.write(f"- {line}")
    if context["verification_valid"]:
        st.success(
            "Independent check passed: order quantities, cost, cash and totals all reconcile (0 violations)."
        )
    else:
        st.error("Independent check failed: " + "; ".join(context["verification_violations"]))


def render_evidence(context: dict) -> None:
    section_title("What we read", "Facts stay linked to the exact words in the original message.")
    st.markdown(
        f'<div class="bb-quote">{quote_html(context["source_text"])}</div>',
        unsafe_allow_html=True,
    )
    if context["evidence"]:
        st.dataframe(
            [
                {
                    "Fact": str(fact["field"]).replace("_", " ").capitalize(),
                    "Captured value": fact["value"],
                    "Exact words in the message": fact["evidence_span"],
                    "Basis": str(fact.get("confidence", "reported")).replace("_", " "),
                }
                for fact in context["evidence"]
            ],
            width="stretch",
            hide_index=True,
        )
        with st.expander("Exact character offsets"):
            st.dataframe(
                [
                    {
                        "Fact": fact["field"],
                        "Captured value": fact["value"],
                        "Start": fact.get("span_start"),
                        "End": fact.get("span_end"),
                    }
                    for fact in context["evidence"]
                ],
                width="stretch",
                hide_index=True,
            )
    left, right = st.columns(2)
    with left:
        section_title("What the plan assumes")
        for assumption in context["assumptions"]:
            st.write(f"- {assumption}")
        if not context["assumptions"]:
            st.caption("No planning assumptions recorded.")
    with right:
        section_title("What is still unknown")
        for unknown in context["unknowns"]:
            st.write(f"- {unknown}")
        if not context["unknowns"]:
            st.caption("No unresolved facts recorded.")
    for warning in context["warnings"]:
        st.warning(warning)


def render_policies(context: dict) -> None:
    mode = context.get("decision_mode")
    relations = {row.get("relation") for row in context.get("policy_basis") or []}
    if mode == "policy_grounded_llm":
        description = (
            "These are the rules the model was allowed to use. 'Cited' means the model referenced the passage "
            "in its answer; the application checked every citation against this set."
        )
    elif context.get("advisory_context") is not None:
        description = (
            "These rules are listed for reference only. The deterministic rule chose the outcome without reading "
            "them and without calling a model, so nothing below influenced the choice."
        )
    elif relations <= {"reference", "in_force"} and "reference" in relations:
        description = "Related policy and precedent passages for this review."
    else:
        description = (
            "Rules in force for this event, supplier and decision date. The fixed ranking did not read them; "
            "they are shown so a reviewer can see the governing policy."
        )
    section_title("Policy basis", description)
    if context.get("references_error"):
        st.warning(context["references_error"])
    basis = context.get("policy_basis") or []
    if not basis:
        st.caption("No policy passage matched this decision.")
    for reference in basis:
        label, tone = _RELATION_BADGES.get(reference.get("relation"), ("Policy", "neutral"))
        with st.container(border=True):
            st.markdown(
                f"{badge(reference['document_id'])} &nbsp; {badge(label, tone)} &nbsp; "
                f"**{escape(reference['title'])}**",
                unsafe_allow_html=True,
            )
            version = f" · version {reference['version']}" if reference.get("version") else ""
            st.caption(f"{reference.get('section') or 'Document overview'} · effective {reference['effective_from']}{version}")
            st.markdown(
                f'<div class="bb-quote">{quote_html(reference["quote"])}</div>',
                unsafe_allow_html=True,
            )
            if reference.get("source_url"):
                st.caption(f"Source: {reference['source_url']} · {reference['licence']}")
            else:
                st.caption(reference["licence"])
    pending = context.get("pending_policies") or []
    if pending:
        with st.expander(f"Written but not yet in force ({len(pending)})"):
            st.caption(
                "These documents are approved but take effect after this decision date, so they do not govern "
                "the recommended plan."
            )
            for item in pending:
                st.markdown(
                    f"{badge(item['document_id'])} &nbsp; **{escape(item['title'])}** — "
                    f"effective {item['effective_from']}",
                    unsafe_allow_html=True,
                )


def render_allocations(context: dict) -> None:
    section_title("Order-by-order fulfilment", "Stock and supplier quantities add up to the plan totals.")
    st.dataframe(
        [
            {
                "Order": row["order_id"],
                "Promised date": row["requested_delivery_date"],
                "Ordered": row["requested_units"],
                "From stock": row["stock_fulfilled_units"],
                "Bought in": row["supplier_fulfilled_units"],
                "Arriving late": row["late_units"],
                "Unfilled": row["unmet_units"],
            }
            for row in context["allocations"]
        ],
        width="stretch",
        hide_index=True,
    )


def render_case(context: dict) -> None:
    case = context["case_context"]
    section_title("Complaint assessment", "Match the report to an order without guessing or sending a reply.")
    columns = st.columns(3)
    columns[0].metric("Retailer", case.get("retailer_id") or "Unknown")
    columns[1].metric("Product", case.get("sku_id") or "Unresolved")
    columns[2].metric("Orders that match", case["matched_order_count"])
    retail = context.get("retail_context") or {}
    if retail.get("case_id"):
        st.caption(
            f"Durable case {retail['case_id']} · priority {case.get('priority', 'normal')} · "
            f"reply draft {retail.get('draft_id') or 'not available'}"
        )
        if case.get("priority_reasons"):
            st.write("Why this priority: " + "; ".join(case["priority_reasons"]))
    if case.get("matched_orders"):
        st.dataframe(case["matched_orders"], width="stretch", hide_index=True)
    if context.get("question"):
        st.info(context["question"])
    elif case.get("clarification_slot"):
        st.warning(f"Clarification required: {case['clarification_slot'].replace('_', ' ')}")
    st.caption("No refund, replacement, stock change or outbound reply is executed.")


def render_market_signal(context: dict) -> None:
    market = context["market_context"]
    section_title("Reported market signal", "Evidence is grouped for review and stays explicitly unverified.")
    if market["signal_type"] == "competitor_observation":
        columns = st.columns(3)
        columns[0].metric("Unique reports", market["unique_observation_count"])
        columns[1].metric("Distinct reporters", market["distinct_reporter_count"])
        columns[2].metric("Corroboration", market["corroboration"].replace("_", " "))
        st.dataframe(market["observations"], width="stretch", hide_index=True)
    else:
        columns = st.columns(3)
        columns[0].metric("Distinct retailers", market["distinct_retailer_count"])
        columns[1].metric("Reported requests", market["reported_request_count"])
        columns[2].metric("Catalogue match", "Yes" if market["catalogue_match"] else "No")
        st.write(f"**Requested pack:** {market['requested_product_label']}")
        stock = market.get("stock_check") or {}
        if stock.get("status") == "indicative_only":
            st.info(
                f"Indicative stock check: {stock['available_units']} base units available, "
                f"{stock['allocated_to_open_orders_units']} allocated to open orders, "
                f"{stock['unallocated_units']} unallocated. This does not confirm an order or reserve stock."
            )
        st.dataframe(market["requests"], width="stretch", hide_index=True)
    st.warning("Reported and unverified: no pricing, procurement, supplier-availability, or assortment decision is inferred.")


def render_advisory(context: dict) -> None:
    advisory = context["advisory_context"]
    section_title(
        "Review assessment",
        "The figures come from the versioned synthetic records; nothing is changed by this review.",
    )
    metrics = advisory.get("metrics") or []
    if metrics:
        columns = st.columns(len(metrics))
        for column, metric in zip(columns, metrics):
            column.metric(metric["label"], metric["value"], metric.get("note") or None)
    for section in advisory.get("sections") or []:
        section_title(section["title"], section.get("description", ""))
        rows = section.get("rows") or []
        if rows:
            st.dataframe(rows, width="stretch", hide_index=True)
        else:
            st.caption("No matching records.")
    st.caption("No credit, price, stock, dispatch or outbound-message action is executed by this review.")


def render_decision_abstention(context: dict) -> None:
    decision = context.get("decision") or {}
    section_title("No recommendation this time", "The selected mode did not produce a verified eligible option.")
    st.warning(decision.get("abstain_reason") or "No verified eligible candidate was available.")
    candidates = context.get("candidate_plans") or []
    if candidates:
        st.dataframe(
            [
                {
                    "Option": row["candidate_id"],
                    "Fulfils": row["fulfilled_units"],
                    "Late": row["late_units"],
                    "Unfilled": row["unmet_units"],
                    "Cost": _money(row["total_cost_rupees"]),
                    "Arrival (estimate)": (row.get("supplier_option") or {}).get("scenario_arrival_date") or "—",
                }
                for row in candidates
            ],
            width="stretch",
            hide_index=True,
        )
    st.caption("No mode fallback was applied. Choose a mode explicitly and run the case again after resolving the issue.")


def render_review_context(context: dict | None, show_summary: bool = True) -> None:
    if not context:
        return
    if show_summary:
        render_operator_summary(context)
    render_decision_steps(context)
    kind = context.get("review_kind")
    if kind == "case_review":
        review_tab, evidence_tab, policies_tab = st.tabs(
            ["Assessment", "Evidence & unknowns", "Policy basis"]
        )
        with review_tab:
            render_case(context)
        with evidence_tab:
            render_evidence(context)
        with policies_tab:
            render_policies(context)
        return
    if kind == "market_signal_review":
        review_tab, evidence_tab, policies_tab = st.tabs(
            ["Assessment", "Evidence & unknowns", "Policy basis"]
        )
        with review_tab:
            render_market_signal(context)
        with evidence_tab:
            render_evidence(context)
        with policies_tab:
            render_policies(context)
        return
    if kind in ADVISORY_KINDS:
        review_tab, evidence_tab, policies_tab = st.tabs(
            ["Assessment", "Evidence & unknowns", "Policy basis"]
        )
        with review_tab:
            render_advisory(context)
        with evidence_tab:
            render_evidence(context)
        with policies_tab:
            render_policies(context)
        return
    if kind == "decision_abstention":
        render_decision_abstention(context)
        evidence_tab, policies_tab = st.tabs(["Evidence & unknowns", "Policy basis"])
        with evidence_tab:
            render_evidence(context)
        with policies_tab:
            render_policies(context)
        return
    decision_tab, evidence_tab, policies_tab, allocations_tab = st.tabs(
        ["Decision", "Evidence & unknowns", "Policy basis", "Order allocation"]
    )
    with decision_tab:
        render_decision(context)
    with evidence_tab:
        render_evidence(context)
    with policies_tab:
        render_policies(context)
    with allocations_tab:
        render_allocations(context)
