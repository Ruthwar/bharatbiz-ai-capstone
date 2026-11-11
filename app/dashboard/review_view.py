"""Shared rendering for the human review card. One view, so the queue and dashboard cannot drift."""

from datetime import date
from decimal import Decimal

import streamlit as st

RANKING_RULE = (
    "Ranking: fewest unmet units, then fewest late units, then earliest arrival, then lowest cost. "
    "When coverage and lateness tie, an earlier arrival wins even if it costs more."
)


def _money(value) -> str:
    return f"₹{Decimal(str(value)):,.2f}"


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


def render_review_context(context: dict | None) -> None:
    if not context:
        return

    unit = context["unit"]
    arrival = context.get("selected_arrival_date")
    st.write(
        f"**Why this plan:** {context['usable_units']} {unit} usable covers "
        f"{min(context['usable_units'], context['requested_units'])} of {context['requested_units']} {unit} "
        f"requested across {context['order_count']} orders; buying {context['required_units']} {unit} leaves "
        f"{context['selected_unmet_units']} unmet and {context['selected_late_units']} late"
        + (f", arriving {arrival}." if arrival else ".")
    )

    st.dataframe(
        [
            {
                "Plan": row["label"] + (" (selected)" if row["selected"] else ""),
                "Cost": _money(row["total_cost_rupees"]),
                "Arrival": row["arrival_date"] or "—",
                "Late": row["late_units"],
                "Unmet": row["unmet_units"],
                "Cash after": _money(row["ending_cash_rupees"]),
                "Headroom": _money(row["headroom_rupees"]),
            }
            for row in context["alternatives"]
        ],
        use_container_width=True,
        hide_index=True,
    )
    st.caption(RANKING_RULE)

    for line in _trade_offs(context):
        st.write(f"- {line}")

    if context["verification_valid"]:
        st.success("Independently verified: allocations, cost, cash and totals — 0 violations.")
    else:
        st.error("Verification failed: " + "; ".join(context["verification_violations"]))

    with st.expander("Evidence from the message"):
        st.caption(context["source_text"])
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
                use_container_width=True,
                hide_index=True,
            )

    with st.expander("Assumptions and unknowns"):
        for assumption in context["assumptions"]:
            st.write(f"- {assumption}")
        for unknown in context["unknowns"]:
            st.write(f"- **Unknown:** {unknown}")
        for warning in context["warnings"]:
            st.warning(warning)

    with st.expander("Per-order allocation"):
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
            use_container_width=True,
            hide_index=True,
        )
