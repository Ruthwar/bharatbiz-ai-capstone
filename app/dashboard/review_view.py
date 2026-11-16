"""Shared rendering for the human review workspace. Pure presentation, no decision logic."""

from datetime import date
from decimal import Decimal
from html import escape

import streamlit as st

from app.dashboard.theme import badge, format_rupees, quote_html, section_title

RANKING_RULE = (
    "Ranking: fewest unmet units, then fewest late units, then earliest arrival, then lowest cost. "
    "When coverage and lateness tie, an earlier arrival wins even if it costs more."
)


def _money(value) -> str:
    return format_rupees(value)


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
                    f"{_money(extra_cost)} more than {alternative['label']} avoids {avoided} late {unit} "
                    f"({_money(per_unit)} per {unit}).",
                )
            )
        elif alternative["late_units"] == selected["late_units"] and selected_arrival and alternative["arrival_date"]:
            days = (date.fromisoformat(alternative["arrival_date"]) - date.fromisoformat(selected_arrival)).days
            if days > 0:
                unit_word = "day" if days == 1 else "days"
                lines.append(
                    (
                        extra_cost,
                        f"{_money(extra_cost)} more than {alternative['label']} arrives {days} {unit_word} earlier "
                        f"({selected_arrival} vs {alternative['arrival_date']}).",
                    )
                )
    return [text for _, text in sorted(lines)]


def _render_infeasible(context: dict) -> None:
    section_title("No feasible plan", "Hard constraints left nothing that can be submitted for approval.")
    reasons = context.get("infeasibility_reasons") or ["No candidate satisfied the hard constraints."]
    st.error("Infeasible: " + "; ".join(reasons))
    comparison = context.get("planner_comparison") or {}
    if comparison:
        agreement = "agree" if comparison.get("planners_agree") else "disagree"
        st.caption(
            f"Deterministic ranking and OR-Tools {agreement}. "
            f"OR-Tools status: {comparison.get('ortools_status') or 'unknown'}."
        )
    for line in comparison.get("constraint_checks") or []:
        st.write(f"- {line}")
    exclusions = context.get("excluded_candidates") or []
    if exclusions:
        st.dataframe(
            [
                {
                    "Candidate": row["candidate_id"],
                    "Supplier": row.get("supplier_id") or "—",
                    "Reasons": ", ".join(row["reasons"]),
                    "Details": "; ".join(f"{key}={value}" for key, value in row.get("details", {}).items()),
                }
                for row in exclusions
            ],
            width="stretch",
            hide_index=True,
        )


def render_decision(context: dict) -> None:
    if context.get("planning_status") == "infeasible":
        _render_infeasible(context)
        return
    unit = context["unit"]
    arrival = context.get("selected_arrival_date")
    section_title("Plan comparison", "Every feasible candidate remains visible; excluded plans never enter ranking.")
    st.write(
        f"{context['usable_units']} {unit} of usable stock covers "
        f"{min(context['usable_units'], context['requested_units'])} of {context['requested_units']} {unit} "
        f"requested across {context['order_count']} orders. The immediate supply gap is {context['required_units']} {unit}. "
        f"The selected plan leaves {context['selected_unmet_units']} unmet and {context['selected_late_units']} late"
        + (f", with arrival on {arrival}." if arrival else ".")
    )
    st.dataframe(
        [
            {
                "Plan": row["label"] + (" · selected" if row["selected"] else ""),
                "Cost": _money(row["total_cost_rupees"]),
                "Arrival": row["arrival_date"] or "—",
                "Late": row["late_units"],
                "Unmet": row["unmet_units"],
                "Cash after": _money(row["ending_cash_rupees"]),
                "Headroom": _money(row["headroom_rupees"]),
            }
            for row in context["alternatives"]
        ],
        width="stretch",
        hide_index=True,
    )
    st.caption(RANKING_RULE)
    comparison = context.get("planner_comparison") or {}
    if comparison.get("ortools_status"):
        if comparison.get("planners_agree"):
            st.caption(
                f"OR-Tools selects the same candidate ({comparison.get('ortools_candidate_id')}), "
                f"status {comparison['ortools_status']}."
            )
        else:
            st.warning(
                "OR-Tools selected "
                f"{comparison.get('ortools_candidate_id') or 'no candidate'}, "
                f"while deterministic ranking selected {comparison.get('deterministic_candidate_id')}."
            )
    exclusions = context.get("excluded_candidates") or []
    if exclusions:
        section_title("Excluded candidates", "Infeasible options remain visible with their exact exclusion reasons.")
        st.dataframe(
            [
                {
                    "Candidate": row["candidate_id"],
                    "Supplier": row.get("supplier_id") or "—",
                    "Reasons": ", ".join(row["reasons"]),
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
            "Counterfactual: receipts on time",
            "Expected receipt dates replace actual dates only in this separate simulation; the operational plan is unchanged.",
        )
        columns = st.columns(5)
        columns[0].metric("Candidate", selected["candidate_id"])
        columns[1].metric("Fulfilled", selected["fulfilled_units"])
        columns[2].metric("Late", selected["late_units"])
        columns[3].metric("Unmet", selected["unmet_units"])
        columns[4].metric("Cost", _money(selected["total_cost_rupees"]))
        st.caption(
            f"Ending cash {_money(selected['cash_projection']['ending_cash_rupees'])} · "
            f"{len(counterfactual.get('excluded_candidates') or [])} excluded candidates · "
            f"verification {'passed' if counterfactual['verification']['valid'] else 'failed'}"
        )
    if context.get("scenario_view") or context.get("cash_schedule"):
        with st.expander("Scenario overlays and dated cash schedule"):
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
        st.success("Independent verification passed: allocations, cost, cash and totals · 0 violations.")
    else:
        st.error("Verification failed: " + "; ".join(context["verification_violations"]))


def render_evidence(context: dict) -> None:
    section_title("Source message", "Facts remain linked to exact spans in the original text.")
    st.markdown(
        f'<div class="bb-quote">{quote_html(context["source_text"])}</div>',
        unsafe_allow_html=True,
    )
    if context["evidence"]:
        st.dataframe(
            [
                {
                    "Field": fact["field"],
                    "Value": fact["value"],
                    "Exact evidence": fact["evidence_span"],
                    "Offsets": (
                        f"{fact['span_start']}–{fact['span_end']}"
                        if fact.get("span_start") is not None
                        else ""
                    ),
                }
                for fact in context["evidence"]
            ],
            width="stretch",
            hide_index=True,
        )
    left, right = st.columns(2)
    with left:
        section_title("Assumptions")
        for assumption in context["assumptions"]:
            st.write(f"- {assumption}")
        if not context["assumptions"]:
            st.caption("No planning assumptions recorded.")
    with right:
        section_title("Unknowns")
        for unknown in context["unknowns"]:
            st.write(f"- {unknown}")
        if not context["unknowns"]:
            st.caption("No unresolved facts recorded.")
    for warning in context["warnings"]:
        st.warning(warning)


def render_policies(context: dict) -> None:
    section_title(
        "Policy and precedent",
        "Retrieved text explains the recommendation. It never supplies quantities, prices or dates to the planner.",
    )
    references = context.get("references") or []
    if context.get("references_error"):
        st.warning(context["references_error"])
    if not references:
        st.caption("No policy section matched this decision.")
    for reference in references:
        with st.container(border=True):
            st.markdown(
                f"{badge(reference['document_id'])} &nbsp; **{escape(reference['title'])}**",
                unsafe_allow_html=True,
            )
            section = reference.get("section") or "Document overview"
            st.caption(f"{section} · effective {reference['effective_from']}")
            st.markdown(
                f'<div class="bb-quote">{quote_html(reference["quote"])}</div>',
                unsafe_allow_html=True,
            )
            if reference.get("source_url"):
                st.caption(f"Source: {reference['source_url']} · {reference['licence']}")
            else:
                st.caption(reference["licence"])


def render_allocations(context: dict) -> None:
    section_title("Per-order allocation", "Stock and supplier quantities reconcile to the plan totals.")
    st.dataframe(
        [
            {
                "Order": row["order_id"],
                "Due": row["requested_delivery_date"],
                "Requested": row["requested_units"],
                "From stock": row["stock_fulfilled_units"],
                "From supplier": row["supplier_fulfilled_units"],
                "Late": row["late_units"],
                "Unmet": row["unmet_units"],
            }
            for row in context["allocations"]
        ],
        width="stretch",
        hide_index=True,
    )


def render_case(context: dict) -> None:
    case = context["case_context"]
    section_title("Complaint assessment", "Match the report to an order without guessing or executing a retailer response.")
    columns = st.columns(3)
    columns[0].metric("Retailer", case.get("retailer_id") or "Unknown")
    columns[1].metric("SKU", case.get("sku_id") or "Unresolved")
    columns[2].metric("Matching orders", case["matched_order_count"])
    retail = context.get("retail_context") or {}
    if retail.get("case_id"):
        st.caption(
            f"Durable case {retail['case_id']} · priority {case.get('priority', 'normal')} · "
            f"reply draft {retail.get('draft_id') or 'not available'}"
        )
        if case.get("priority_reasons"):
            st.write("Priority reasons: " + "; ".join(case["priority_reasons"]))
    if case.get("matched_orders"):
        st.dataframe(case["matched_orders"], width="stretch", hide_index=True)
    if context.get("question"):
        st.info(context["question"])
    elif case.get("clarification_slot"):
        st.warning(f"Clarification required: {case['clarification_slot'].replace('_', ' ')}")
    st.caption("No refund, replacement, stock mutation, or outbound response is executed.")


def render_market_signal(context: dict) -> None:
    market = context["market_context"]
    section_title("Reported market signal", "Evidence is aggregated for review and remains explicitly unverified.")
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


def render_review_context(context: dict | None) -> None:
    if not context:
        return
    if context.get("review_kind") == "case_review":
        render_case(context)
    elif context.get("review_kind") == "market_signal_review":
        render_market_signal(context)
    elif context.get("planning_status") == "infeasible":
        render_decision(context)
    else:
        render_decision(context)
        render_allocations(context)
    render_evidence(context)
    render_policies(context)
