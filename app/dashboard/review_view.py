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


def render_decision(context: dict) -> None:
    unit = context["unit"]
    arrival = context.get("selected_arrival_date")
    section_title("Plan comparison", "Every feasible candidate remains visible; excluded plans never enter ranking.")
    st.write(
        f"{context['usable_units']} {unit} of usable stock covers "
        f"{min(context['usable_units'], context['requested_units'])} of {context['requested_units']} {unit} "
        f"requested across {context['order_count']} orders. Buying {context['required_units']} {unit} leaves "
        f"{context['selected_unmet_units']} unmet and {context['selected_late_units']} late"
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


def render_review_context(context: dict | None) -> None:
    if not context:
        return
    render_decision(context)
    render_evidence(context)
    render_policies(context)
    render_allocations(context)
