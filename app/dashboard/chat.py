import csv
import json
import os
import sys
import urllib.error
import urllib.request
from html import escape
from pathlib import Path

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.dashboard.evaluation_view import render_evaluation  # noqa: E402
from app.dashboard.observability_view import render_observability  # noqa: E402
from app.dashboard.retail_view import render_retail_desk  # noqa: E402
from app.dashboard.review_view import (  # noqa: E402
    ADVISORY_KINDS,
    render_advisory,
    render_allocations,
    render_case,
    render_decision,
    render_decision_abstention,
    render_decision_steps,
    render_evidence,
    render_market_signal,
    render_policies,
    render_review_context,
)
from app.dashboard.theme import (  # noqa: E402
    apply_theme,
    badge,
    empty_state,
    format_rupees as money,
    metric_card,
    page_header,
    quote_html,
    section_title,
)
from app.orchestration.review import build_review_context  # noqa: E402
from app.rag.corpus import DOC_TYPES, load_documents  # noqa: E402
from app.rag.retrieval import retrieve  # noqa: E402
from app.state import StateLoadError, load_business_state  # noqa: E402
from app.units import unit_word  # noqa: E402

API_URL = os.getenv("BHARATBIZ_API_URL", "http://127.0.0.1:8000")
PAGES = [
    "Overview",
    "Inbox",
    "Scenario lab",
    "Decision desk",
    "Retail desk",
    "Operations data",
    "Evaluation",
    "LLM observability",
    "Knowledge",
]

st.set_page_config(page_title="BharatBiz Operations", layout="wide", initial_sidebar_state="expanded")
apply_theme()


def post(path: str, payload: dict) -> dict:
    request = urllib.request.Request(
        f"{API_URL}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=45) as response:
        return json.loads(response.read().decode("utf-8"))


def patch(path: str, payload: dict) -> dict:
    request = urllib.request.Request(
        f"{API_URL}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="PATCH",
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def get(path: str):
    with urllib.request.urlopen(f"{API_URL}{path}", timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def safe_get(path: str, fallback):
    try:
        return get(path)
    except (urllib.error.URLError, TimeoutError, ValueError):
        return fallback


def go_to(page: str) -> None:
    st.session_state.next_page = page
    st.rerun()


@st.dialog("Reset demo data?")
def confirm_demo_reset() -> None:
    st.write(
        "This clears displayed scenario results, inbox chats, unfinished conversations, "
        "the review queue, retailer cases, reply drafts, market observations and model traces."
    )
    st.caption("The fifteen source fixtures, base business data, knowledge corpus and evaluation results are preserved.")
    cancel_column, reset_column = st.columns(2)
    if cancel_column.button("Cancel", width="stretch"):
        st.rerun()
    if reset_column.button("Yes, reset demo", type="primary", width="stretch"):
        try:
            post("/api/v1/demo/reset", {})
        except urllib.error.HTTPError as exc:
            st.error(f"API returned {exc.code}: {exc.read().decode('utf-8')}")
        except (urllib.error.URLError, TimeoutError) as exc:
            st.error(f"Cannot reset the demo through the API at {API_URL}: {exc}")
        else:
            st.session_state.clear()
            st.session_state.next_page = "Overview"
            st.rerun()


def inventory_rows(state) -> list[dict]:
    products = {row["sku_id"]: row for row in state.products}
    demand = {}
    for order in state.open_orders:
        demand[order["sku_id"]] = demand.get(order["sku_id"], 0) + order["quantity_units"]
    rows = []
    for row in state.inventory:
        available = row["on_hand_units"] - row["reserved_units"]
        open_demand = demand.get(row["sku_id"], 0)
        projected = available + row["incoming_units"]
        net_position = projected - open_demand
        product = products[row["sku_id"]]
        rows.append(
            {
                "SKU": row["sku_id"],
                "Product": f"{product['product_name']} · {product['pack_description']}",
                "On hand": row["on_hand_units"],
                "Reserved": row["reserved_units"],
                "Available": available,
                "Incoming": row["incoming_units"],
                "Open demand": open_demand,
                "Net position": net_position,
                "Shortfall": max(0, -net_position),
                "Reorder point": row["reorder_point_units"],
                "Unit": row["unit"],
                "Status": "Supply gap" if net_position < 0 else "Supplier needed" if available < open_demand else "Covered",
            }
        )
    return rows


def order_rows(state) -> list[dict]:
    retailers = {row["retailer_id"]: row for row in state.retailers}
    products = {row["sku_id"]: row for row in state.products}
    rows = []
    for row in state.open_orders:
        retailer = retailers.get(row["retailer_id"], {})
        product = products.get(row["sku_id"], {})
        rows.append(
            {
                "Order": row["order_id"],
                "Retailer": retailer.get("retailer_name", row["retailer_id"]),
                "Area": retailer.get("area", ""),
                "SKU": row["sku_id"],
                "Product": product.get("pack_description", ""),
                "Due": row["requested_delivery_date"],
                "Quantity": row["quantity_units"],
                "Unit": row["unit"],
                "Priority": row["priority"],
                "Status": row["status"],
            }
        )
    return sorted(rows, key=lambda row: (row["Due"], row["Order"]))


def render_overview(state, review_items: list[dict], stock: list[dict], orders: list[dict]) -> None:
    page_header(
        "Control room",
        "Operations overview",
        "A single view of demand, stock exposure, cash protection and decisions waiting for a person.",
        f"As of {state.as_of:%d %b %Y} · Synthetic workspace",
    )
    gaps = [row for row in stock if row["Status"] == "Supply gap"]
    high_priority = sum(row["Priority"] == "high" for row in orders)
    headroom = state.cash_balance_rupees - state.minimum_cash_buffer_rupees
    columns = st.columns(5)
    with columns[0]:
        metric_card("Open order lines", str(len(orders)), f"{high_priority} high priority", "accent")
    with columns[1]:
        metric_card("Demand gaps", str(len(gaps)), "Open demand exceeds available + incoming", "warning" if gaps else "success")
    with columns[2]:
        metric_card("Pending review", str(len(review_items)), "Human decision required", "warning" if review_items else "success")
    with columns[3]:
        metric_card("Cash on hand", money(state.cash_balance_rupees), "Opening simulation balance")
    with columns[4]:
        metric_card("Deployable cash", money(headroom), f"Above {money(state.minimum_cash_buffer_rupees)} buffer", "success")

    st.write("")
    left, right = st.columns([1.45, 1])
    with left:
        with st.container(border=True):
            section_title("Needs attention", "Exceptions first; routine records stay in Operations data.")
            entries = []
            for item in review_items[:3]:
                entries.append(
                    f"<li><div class='bb-list-title'>{escape(item['summary'])}</div>"
                    f"<div class='bb-list-meta'>{escape(item['event_type'].replace('_', ' ').title())} · "
                    f"{escape(item['event_id'])} · awaiting review</div></li>"
                )
            for row in gaps[:3]:
                entries.append(
                    f"<li><div class='bb-list-title'>{escape(row['Product'])}</div>"
                    f"<div class='bb-list-meta'>{row['Shortfall']} {escape(row['Unit'])} short after incoming · "
                    f"{row['Open demand']} {escape(row['Unit'])} open demand</div></li>"
                )
            if entries:
                st.markdown(f"<ul class='bb-list'>{''.join(entries)}</ul>", unsafe_allow_html=True)
            else:
                empty_state("No exceptions", "No stock gaps or pending decisions.")
            if review_items and st.button("Open decision desk", type="primary"):
                go_to("Decision desk")
    with right:
        with st.container(border=True):
            section_title("Cash protection", "The minimum buffer is excluded before any plan is ranked.")
            st.write(f"**{money(state.cash_balance_rupees)}** opening cash")
            deployable_percent = max(0, min(100, int(headroom / state.cash_balance_rupees * 100)))
            st.markdown(
                f"<div class='bb-meter'><div class='bb-meter-fill' style='width:{deployable_percent}%'></div></div>"
                f"<div class='bb-meter-legend'><span>Buffer {money(state.minimum_cash_buffer_rupees)}</span>"
                f"<span>{deployable_percent}% deployable</span></div>",
                unsafe_allow_html=True,
            )
            st.write("")
            st.write(f"**{money(headroom)}** available above the floor")
            st.caption("No payment, credit decision or cash mutation is executed by this console.")

    left, right = st.columns([1, 1.35])
    with left:
        with st.container(border=True):
            section_title("Inventory watchlist", "Open demand compared with available stock plus incoming supply.")
            st.dataframe(
                [
                    {
                        "Product": row["Product"],
                        "Demand": f"{row['Open demand']} {row['Unit']}",
                        "Available + incoming": row["Available"] + row["Incoming"],
                        "Shortfall": row["Shortfall"],
                    }
                    for row in gaps
                ] or [{"Product": "All open demand covered", "Demand": "—", "Available + incoming": "—", "Shortfall": "—"}],
                width="stretch",
                hide_index=True,
            )
    with right:
        with st.container(border=True):
            section_title("Next orders due", "Retailer, product and priority in one order book.")
            st.dataframe(
                [
                    {
                        "Order": row["Order"],
                        "Retailer": row["Retailer"],
                        "Product": row["Product"],
                        "Due": row["Due"],
                        "Qty": f"{row['Quantity']} {row['Unit']}",
                        "Priority": row["Priority"],
                    }
                    for row in orders[:7]
                ],
                width="stretch",
                hide_index=True,
            )

    with st.container(border=True):
        section_title("Controlled decision flow", "Model extraction is optional; operational decisions remain deterministic and reviewable.")
        steps = ["Channel intake", "Evidence extraction", "Candidate planning", "Independent verification", "Human decision"]
        flow = []
        for index, step in enumerate(steps):
            flow.append(f"<span class='bb-flow-step'>{index + 1}. {escape(step)}</span>")
            if index < len(steps) - 1:
                flow.append("<span class='bb-flow-arrow'>→</span>")
        st.markdown(f"<div class='bb-flow'>{''.join(flow)}</div>", unsafe_allow_html=True)


def render_processing_result(result: dict | None) -> None:
    if not result:
        empty_state("No message processed", "Send a message to see its route, evidence and recommendation.")
        return
    event = result.get("event") or {}
    st.markdown(
        f"{badge(event.get('event_type', 'unclassified').replace('_', ' '), 'warning')} "
        f"{badge(result.get('mode', 'unknown'))}",
        unsafe_allow_html=True,
    )
    st.caption(f"Route: {result.get('routed_action')} · clarification rounds: {result.get('rounds', 0)}")
    if result.get("processing_error"):
        st.error(f"{result['processing_error']} — queued for human triage.")
    if result.get("question"):
        st.info(result["question"])
    if event.get("extracted_facts"):
        section_title("Extracted evidence")
        st.dataframe(
            [
                {"Field": fact["field"], "Value": fact["value"], "Evidence": fact["evidence_span"]}
                for fact in event["extracted_facts"]
            ],
            width="stretch",
            hide_index=True,
        )
    for uncertainty in event.get("uncertainties", []):
        st.warning(uncertainty)
    recommendation = result.get("recommendation")
    if recommendation:
        section_title("Recommendation", "Pending human review; nothing has executed.")
        st.write(recommendation["summary"])
        if st.button("Review this decision", type="primary"):
            st.session_state.selected_case_id = event.get("event_id")
            go_to("Decision desk")


def _load_inbox_example(example: dict, sender_label: str) -> None:
    message = example["message"]
    st.session_state.inbox_sender = sender_label
    st.session_state.inbox_language = message["language"]
    st.session_state.inbox_conversation = f"demo-{example['scenario_id'].lower()}"
    st.session_state.message_draft = message["text"]
    st.session_state.last_result = None
    st.session_state.chat = []


def render_inbox(parties: list[dict], scenarios: list[dict]) -> None:
    page_header(
        "Channel workspace",
        "Message inbox",
        "Simulate a supplier or retailer update, inspect the extracted evidence, and send the resulting case to review.",
        "Demo channel · identity is selected, not authenticated",
    )
    examples = {row["scenario_id"]: row for row in scenarios if row.get("message")}
    sender_labels = {}
    with st.container(border=True):
        section_title("Intake controls", "A production channel would derive the sender from the authenticated account.")
        sender_column, language_column, conversation_column = st.columns([2, 1, 1.4])
        if parties:
            labels = {
                f"{party['party_name']} · {party['party_type']} · {party['party_id']}": party
                for party in parties
            }
            sender_labels = {
                (party["party_type"], party["party_id"]): label
                for label, party in labels.items()
            }
            for scenario_id, example in examples.items():
                message = example["message"]
                key = (message["sender_type"], message["sender_id"])
                if key not in sender_labels:
                    party_name = f"{scenario_id} field reporter" if key[1] else "Synthetic planning desk"
                    label = f"{party_name} · {key[0]} · {key[1] or 'no reporter ID'}"
                    labels[label] = {
                        "party_name": party_name,
                        "party_type": key[0],
                        "party_id": key[1],
                    }
                    sender_labels[key] = label
            sender = labels[sender_column.selectbox("Sender", list(labels), key="inbox_sender")]
            sender_type, sender_id = sender["party_type"], sender["party_id"]
        else:
            sender_type = sender_column.selectbox("Sender type", ["retailer", "supplier", "sales_rep", "unknown"])
            sender_id = sender_column.text_input("Sender account ID", "SUP-005")
        language = language_column.selectbox("Language", ["English", "Hinglish", "Hindi"], key="inbox_language")
        conversation_id = conversation_column.text_input("Conversation ID", "demo-conversation-1", key="inbox_conversation")

        if examples:
            st.divider()
            section_title(
                "Demo examples",
                "Load an editable intake message, or run the complete fixture to inspect its canonical decision.",
            )
            selected_example_id = st.selectbox(
                "Example scenario",
                list(examples),
                key="inbox_example",
                format_func=lambda scenario_id: f"{scenario_id} · {examples[scenario_id]['name']}",
            )
            example = examples[selected_example_id]
            st.write(example["description"])
            st.caption(f"Expected full-scenario decision: {example['demo_outcome']}")
            load_column, run_column = st.columns(2)
            message = example["message"]
            load_column.button(
                "Load editable example",
                key=f"load-inbox-{selected_example_id}",
                on_click=_load_inbox_example,
                args=(example, sender_labels.get((message["sender_type"], message["sender_id"]), "")),
                disabled=not parties,
                width="stretch",
            )
            if run_column.button(
                "Run full scenario",
                key=f"run-inbox-{selected_example_id}",
                type="primary",
                width="stretch",
            ):
                try:
                    result = post(
                        f"/api/v1/scenarios/{selected_example_id}/run",
                        {
                            "persist_review": False,
                            "decision_mode": st.session_state.get("recommendation_mode", "deterministic"),
                        },
                    )
                except urllib.error.HTTPError as exc:
                    st.error(f"API returned {exc.code}: {exc.read().decode('utf-8')}")
                except urllib.error.URLError as exc:
                    st.error(f"Cannot reach the API at {API_URL}: {exc.reason}")
                else:
                    st.session_state.scenario_result = result
                    st.session_state.scenario_result_id = selected_example_id
                    st.session_state.scenario_result_mode = st.session_state.get("recommendation_mode", "deterministic")
                    st.session_state.scenario_selector = selected_example_id
                    go_to("Scenario lab")
            st.caption("Editable intake processes only the visible message. Run full scenario to include all fixture overlays and assumptions.")

    left, right = st.columns([1.15, 1])
    with left:
        with st.container(border=True):
            section_title("Sandbox conversation", "Only receipt and completion acknowledgements are automated.")
            history = st.session_state.setdefault("chat", [])
            for entry in history:
                with st.chat_message(entry["role"]):
                    st.write(entry["text"])
                    if entry.get("kind"):
                        st.caption(entry["kind"])
            with st.form("message-intake", clear_on_submit=True):
                text = st.text_area(
                    "Message",
                    key="message_draft",
                    placeholder="Write a supplier delay, delivery complaint or stock update…",
                    height=105,
                )
                submitted = st.form_submit_button("Send for processing", type="primary", width="stretch")
            if submitted:
                if not text.strip():
                    st.warning("Write a message before sending.")
                else:
                    payload = {
                        "text": text,
                        "sender_type": sender_type,
                        "sender_id": sender_id,
                        "language": language,
                        "conversation_id": conversation_id,
                        "decision_mode": st.session_state.get("recommendation_mode", "deterministic"),
                    }
                    try:
                        result = post("/api/v1/inbound", payload)
                    except urllib.error.HTTPError as exc:
                        st.error(f"API returned {exc.code}: {exc.read().decode('utf-8')}")
                    except urllib.error.URLError as exc:
                        st.error(f"Cannot reach the API at {API_URL}: {exc.reason}")
                    else:
                        history.append({"role": "user", "text": text})
                        for ack in (result["ack"], result.get("completion_ack")):
                            if ack:
                                history.append({"role": "assistant", "text": ack["text"], "kind": ack["kind"]})
                        if result.get("question"):
                            history.append({"role": "assistant", "text": result["question"], "kind": "question"})
                        st.session_state.last_result = result
                        st.rerun()
    with right:
        with st.container(border=True):
            section_title("Latest processing", "Schema-validated extraction with explicit unknowns.")
            render_processing_result(st.session_state.get("last_result"))


def render_scenario_lab(scenarios: list[dict]) -> None:
    page_header(
        "Selectable decision modes",
        "Scenario lab",
        "Run every capstone scenario through the same extraction, planning, verification and human-review contracts.",
        f"{len(scenarios)} explicit fixtures · base business data is never mutated",
    )
    if not scenarios:
        empty_state("Scenario catalogue unavailable", "Start the API to load and run the scenario fixtures.")
        return
    by_id = {row["scenario_id"]: row for row in scenarios}
    selected_id = st.selectbox(
        "Scenario",
        list(by_id),
        key="scenario_selector",
        format_func=lambda scenario_id: f"{scenario_id} · {by_id[scenario_id]['name']}",
    )
    selected = by_id[selected_id]
    st.write(selected["description"])
    persist = st.checkbox("Persist the outcome in the SQLite review queue", value=True)
    if st.button("Run selected scenario", type="primary"):
        try:
            st.session_state.scenario_result = post(
                f"/api/v1/scenarios/{selected_id}/run",
                {
                    "persist_review": persist,
                    "decision_mode": st.session_state.get("recommendation_mode", "deterministic"),
                },
            )
            st.session_state.scenario_result_id = selected_id
            st.session_state.scenario_result_mode = st.session_state.get("recommendation_mode", "deterministic")
        except urllib.error.HTTPError as exc:
            st.error(f"API returned {exc.code}: {exc.read().decode('utf-8')}")
        except urllib.error.URLError as exc:
            st.error(f"Cannot reach the API at {API_URL}: {exc.reason}")

    result = st.session_state.get("scenario_result")
    if not result:
        empty_state("No scenario run yet", "Select a fixture and run it to inspect the complete decision trace.")
        return
    if st.session_state.get("scenario_result_id") != selected_id:
        st.info("The displayed result is from the previously selected scenario. Run this scenario to replace it.")
    if st.session_state.get("scenario_result_mode") != st.session_state.get("recommendation_mode", "deterministic"):
        st.info("The displayed result used a different recommendation mode. Run the scenario again to use the selected mode.")
    if result.get("decision_mode_applied") is False:
        st.caption("This scenario does not produce an operational plan, so the selected decision mode was not applied.")
    context = build_review_context(result)
    event = result.get("event") or {}
    recommendation = result.get("recommendation") or {}
    event_label = (context or {}).get("event_label") or event.get("event_type", "unclassified").replace("_", " ")
    review_label = (context or {}).get("review_label") or result.get("review_kind", "triage").replace("_", " ")
    mode_label = (context or {}).get("decision_mode_label") or result.get("decision_mode", "deterministic")
    st.markdown(
        f"{badge(event_label, 'warning')} {badge(review_label)} {badge(mode_label)}",
        unsafe_allow_html=True,
    )
    st.caption(
        f"Status: {str(recommendation.get('review_status', 'unknown')).replace('_', ' ')} · "
        f"Event {event.get('event_id')} · Data version {event.get('state_version')} · "
        f"Facts read with {(context or {}).get('extraction_label', 'deterministic extraction')}"
    )
    summary_text = (context or {}).get("operator_summary") or recommendation.get("summary", "")
    st.markdown(
        f"<div class='bb-recommendation'><div class='bb-recommendation-label'>What this means</div>"
        f"<div class='bb-recommendation-text'>{escape(summary_text)}</div></div>",
        unsafe_allow_html=True,
    )
    inbound = result.get("inbound") or {}
    if inbound.get("question"):
        st.info(inbound["question"])
    if inbound:
        st.caption(
            f"Routed to {str(inbound.get('routed_action', 'review')).replace('_', ' ')} · "
            f"status {str(recommendation.get('review_status', 'unknown')).replace('_', ' ')}"
        )
    render_review_context(context, show_summary=False)


def render_draft_review_actions(item: dict) -> None:
    draft_id = item["draft_id"]
    draft = safe_get(f"/api/v1/retail/drafts/{draft_id}", None)
    if not draft:
        st.error("The linked reply draft is unavailable; no review decision was submitted.")
        return
    with st.container(border=True):
        section_title(
            "Retailer reply review",
            "Approve or edit the safe draft. Approval does not send the reply or resolve the case.",
        )
        with st.form(f"decision-draft-{item['event_id']}"):
            final_text = st.text_area("Reply text", draft["final_text"] or draft["text"], height=125)
            reviewer = st.text_input("Reviewer ID", "demo-owner")
            note = st.text_input("Review note")
            approve_column, reject_column = st.columns(2)
            approved = approve_column.form_submit_button("Approve reply", type="primary", width="stretch")
            rejected = reject_column.form_submit_button("Reject reply", width="stretch")
        if approved or rejected:
            try:
                post(
                    f"/api/v1/retail/drafts/{draft_id}/review",
                    {
                        "event_id": item["event_id"],
                        "decision": "approve" if approved else "reject",
                        "reviewer": reviewer,
                        "note": note or None,
                        "final_text": final_text,
                    },
                )
            except urllib.error.HTTPError as exc:
                st.error(f"API returned {exc.code}: {exc.read().decode('utf-8')}")
            except urllib.error.URLError as exc:
                st.error(f"Cannot reach the API at {API_URL}: {exc.reason}")
            else:
                st.toast("Reply review saved; use Retail desk to record a manual send.")
                st.rerun()


def render_review_actions(item: dict, context: dict | None) -> None:
    if item.get("draft_id"):
        render_draft_review_actions(item)
        return
    selected_id = item["event_id"]
    planned = context is not None
    operational = planned and context.get("review_kind") == "operational_plan"
    with st.container(border=True):
        section_title(
            "Reviewer decision" if planned else "Triage decision",
            "Approval changes the demo ledger only." if planned else "Resolve or dismiss this unplanned case in the demo ledger.",
        )
        reviewer = st.text_input("Reviewer ID", "demo-owner", key=f"reviewer-{selected_id}")
        approve_column, reject_column, note_column = st.columns([1, 1, 2.5])
        if approve_column.button(
            "Approve plan" if operational else "Mark reviewed",
            type="primary",
            key=f"approve-{selected_id}",
            disabled=planned and context.get("verification_valid") is False,
            width="stretch",
        ):
            post(f"/api/v1/review/{selected_id}", {"decision": "approve", "reviewer": reviewer})
            st.toast("Case updated in the demo ledger.")
            st.rerun()
        if reject_column.button(
            "Reject plan" if operational else "Dismiss case",
            key=f"reject-{selected_id}",
            width="stretch",
        ):
            post(f"/api/v1/review/{selected_id}", {"decision": "reject", "reviewer": reviewer})
            st.toast("Case dismissed in the demo ledger.")
            st.rerun()
        note_column.caption("No purchase order, payment, stock update or outbound message is executed.")


def render_decision_desk(review_items: list[dict]) -> None:
    page_header(
        "Human-in-the-loop",
        "Decision desk",
        "Compare feasible plans, inspect the source evidence and policy basis, then approve or reject the recommendation.",
        f"{len(review_items)} pending · no autonomous execution",
    )
    if not review_items:
        with st.container(border=True):
            empty_state("Review queue clear", "New recommendations will appear here after intake and verification.")
        return

    queue_column, detail_column = st.columns([0.72, 2.28])
    item_by_id = {item["event_id"]: item for item in review_items}
    with queue_column:
        with st.container(border=True):
            section_title("Review queue", "Oldest received first")
            preferred_id = st.session_state.pop("selected_case_id", None)
            if preferred_id in item_by_id:
                st.session_state.case_selector = preferred_id
            if st.session_state.get("case_selector") not in item_by_id:
                st.session_state.case_selector = next(iter(item_by_id))
            selected_id = st.radio(
                "Pending cases",
                list(item_by_id),
                key="case_selector",
                format_func=lambda event_id: (
                    f"{list(item_by_id).index(event_id) + 1:02d} · "
                    f"{(item_by_id[event_id].get('why') or {}).get('event_label') or item_by_id[event_id]['event_type'].replace('_', ' ').title()}"
                ),
                label_visibility="collapsed",
            )
            st.caption(f"{len(review_items)} cases awaiting a person")
    item = item_by_id[selected_id]
    context = item.get("why")
    with detail_column:
        st.markdown(
            f"{badge('Pending review', 'warning')} "
            f"{badge((context or {}).get('event_label') or item['event_type'].replace('_', ' '))} "
            f"<span class='bb-code'>{escape(item['event_id'])}</span>",
            unsafe_allow_html=True,
        )
        st.caption(
            f"Received {item['received_at']} · data version {item['state_version']} · "
            f"decision {((context or {}).get('decision_mode_label') or item.get('decision_mode') or 'deterministic').lower()} · "
            f"facts {(context or {}).get('extraction_label') or item['mode']}"
        )
        summary_text = (context or {}).get("operator_summary") or item["summary"]
        st.markdown(
            f"<div class='bb-recommendation'><div class='bb-recommendation-label'>What this means</div>"
            f"<div class='bb-recommendation-text'>{escape(summary_text)}</div></div>",
            unsafe_allow_html=True,
        )
        if not context:
            st.warning("This case does not have a structured plan. Review the triage summary before resolving it.")
            render_review_actions(item, None)
            return
        render_decision_steps(context)
        if context.get("review_kind") in {"case_review", "market_signal_review"}:
            review_tab, evidence_tab, policies_tab = st.tabs(["Assessment", "Evidence & unknowns", "Policy basis"])
            with review_tab:
                if context["review_kind"] == "case_review":
                    render_case(context)
                else:
                    render_market_signal(context)
            with evidence_tab:
                render_evidence(context)
            with policies_tab:
                render_policies(context)
            render_review_actions(item, context)
            return
        if context.get("review_kind") in ADVISORY_KINDS:
            review_tab, evidence_tab, policies_tab = st.tabs(["Assessment", "Evidence & unknowns", "Policy basis"])
            with review_tab:
                render_advisory(context)
            with evidence_tab:
                render_evidence(context)
            with policies_tab:
                render_policies(context)
            render_review_actions(item, context)
            return
        if context.get("review_kind") == "decision_abstention":
            render_decision_abstention(context)
            evidence_tab, policies_tab = st.tabs(["Evidence & unknowns", "Policy basis"])
            with evidence_tab:
                render_evidence(context)
            with policies_tab:
                render_policies(context)
            render_review_actions(item, context)
            return
        selected = next((row for row in context["alternatives"] if row["selected"]), None)
        columns = st.columns(5)
        with columns[0]:
            metric_card(
                "Coverage",
                f"{context['selected_fulfilled_units']}/{context['requested_units']}",
                unit_word(context["requested_units"], context["unit"]),
                "accent",
            )
        with columns[1]:
            metric_card(
                "Late",
                str(context["selected_late_units"]),
                unit_word(context["selected_late_units"], context["unit"]),
                "warning",
            )
        with columns[2]:
            metric_card(
                "Unfilled",
                str(context["selected_unmet_units"]),
                unit_word(context["selected_unmet_units"], context["unit"]),
                "danger" if context["selected_unmet_units"] else "success",
            )
        with columns[3]:
            metric_card("Purchase cost", money(context["selected_cost_rupees"]), "Immediate outflow")
        with columns[4]:
            metric_card("Cash left above buffer", money(selected["headroom_rupees"]) if selected else "—", "After procurement", "success")
        st.write("")
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
        render_review_actions(item, context)


def render_operations(state, stock: list[dict], orders: list[dict]) -> None:
    page_header(
        "Synthetic ledger",
        "Operations data",
        "Inspect the exact records used by the planner. Product, retailer and supplier IDs remain stable join keys.",
        f"State {state.state_version}",
    )
    inventory_tab, orders_tab, suppliers_tab, retailers_tab, catalogue_tab, cash_tab = st.tabs(
        ["Inventory", "Open orders", "Suppliers", "Retailers", "Catalogue", "Cash ledger"]
    )
    with inventory_tab:
        section_title("Inventory position", "Available, incoming and reorder thresholds by SKU.")
        st.dataframe(stock, width="stretch", hide_index=True)
    with orders_tab:
        section_title("Open order book", f"{len(orders)} order lines in the simulation state.")
        st.dataframe(orders, width="stretch", hide_index=True)
    with suppliers_tab:
        section_title("Supplier directory", "Lead times and payment terms are context, not supplier credit in the cash projection.")
        offer_counts = {}
        for offer in state.supplier_offers:
            offer_counts[offer["supplier_id"]] = offer_counts.get(offer["supplier_id"], 0) + 1
        st.dataframe(
            [
                {
                    "Supplier": row["supplier_name"],
                    "ID": row["supplier_id"],
                    "Lead days": row["lead_time_days"],
                    "Payment days": row["payment_terms_days"],
                    "Listed SKUs": offer_counts.get(row["supplier_id"], 0),
                }
                for row in state.suppliers
            ],
            width="stretch",
            hide_index=True,
        )
    with retailers_tab:
        section_title("Retailer directory", "Fictional trade names and localities; not verified real businesses.")
        st.dataframe(
            [
                {
                    "Retailer": row["retailer_name"],
                    "ID": row["retailer_id"],
                    "Format": row["shop_type"],
                    "Area": row["area"],
                    "Priority": row["service_priority"],
                }
                for row in state.retailers
            ],
            width="stretch",
            hide_index=True,
        )
    with catalogue_tab:
        section_title("Product catalogue", "Exact units and pack descriptions prevent silent unit conversion.")
        st.dataframe(
            [
                {
                    "SKU": row["sku_id"],
                    "Category": row["category"],
                    "Product": row["product_name"],
                    "Pack": row["pack_description"],
                    "Base unit": row["base_unit"],
                    "Units per case": row["units_per_case"],
                    "Reference cost": money(row["unit_cost_rupees"]),
                }
                for row in state.products
            ],
            width="stretch",
            hide_index=True,
        )
    with cash_tab:
        section_title("Cash ledger", "Synthetic movements; procurement plans treat cost as immediate outflow.")
        with (PROJECT_ROOT / "data" / "synthetic" / "cash_ledger.csv").open(encoding="utf-8-sig", newline="") as handle:
            ledger_rows = list(csv.DictReader(handle))
        st.dataframe(
            [
                {
                    "Entry": row["entry_id"],
                    "Date": row["entry_date"],
                    "Type": row["entry_type"],
                    "Amount": money(row["amount_rupees"]),
                    "Minimum buffer": money(row["minimum_buffer_rupees"]),
                }
                for row in ledger_rows
            ],
            width="stretch",
            hide_index=True,
        )


def render_knowledge() -> None:
    documents = load_documents()
    section_count = sum(len(document.sections) for document in documents)
    page_header(
        "Governed retrieval",
        "Knowledge base",
        "Search approved policies, SOPs, supplier terms, case notes and cited regulatory extracts. Quotes are verbatim.",
        f"{len(documents)} documents · {section_count} sections",
    )
    columns = st.columns(4)
    with columns[0]:
        metric_card("Documents", str(len(documents)), "Curated, not open-web ingestion", "accent")
    with columns[1]:
        metric_card("Searchable sections", str(section_count), "Best section per document")
    with columns[2]:
        metric_card("Document types", str(len(DOC_TYPES)), "Policy to regulation")
    with columns[3]:
        metric_card("Retrieval", "BM25", "Deterministic · local · no embeddings", "success")
    st.write("")
    policies = [document for document in documents if document.doc_type == "policy"]
    in_force = [document for document in policies if document.effective_from <= state.as_of.date().isoformat()]
    pending = [document for document in policies if document.effective_from > state.as_of.date().isoformat()]
    with st.expander(f"Policy state on {state.as_of:%d %b %Y} · {len(in_force)} in force, {len(pending)} pending"):
        st.caption(
            "Effective dates decide which rules can ground a recommendation. Pending rules are written and approved "
            "but are excluded until their effective date."
        )
        st.dataframe(
            [
                {
                    "Policy": document.document_id,
                    "Title": document.title,
                    "Effective": document.effective_from,
                    "State on demo date": "In force" if document in in_force else "Pending",
                }
                for document in policies
            ],
            width="stretch",
            hide_index=True,
        )
    with st.container(border=True):
        query_column, type_column = st.columns([2, 1])
        query = query_column.text_input(
            "Search the approved corpus",
            placeholder="Try: unconfirmed delivery date, maximum retail price, cash buffer",
        )
        selected_types = type_column.multiselect("Document types", DOC_TYPES)
    if not query.strip():
        section_title("Document library", "Every record carries an owner, effective date, classification and licence.")
        st.dataframe(
            [
                {
                    "Document": document.document_id,
                    "Title": document.title,
                    "Type": document.doc_type,
                    "Version": document.version,
                    "Effective": document.effective_from,
                    "Owner": document.owner,
                    "Classification": document.classification,
                    "Sections": len(document.sections),
                }
                for document in documents
            ],
            width="stretch",
            hide_index=True,
        )
        return
    try:
        hits = retrieve(query, top_k=6, doc_types=selected_types or None)
    except Exception as exc:
        st.error(f"The knowledge index is unavailable: {type(exc).__name__}")
        return
    section_title("Search results", f"{len(hits)} documents matched · one best section per document")
    if not hits:
        empty_state("No confident match", "Try more specific policy vocabulary or remove the document-type filter.")
    for hit in hits:
        with st.container(border=True):
            st.markdown(
                f"{badge(hit['document_id'])} {badge(hit['doc_type'].replace('_', ' '))} "
                f"**{escape(hit['title'])}**",
                unsafe_allow_html=True,
            )
            st.caption(f"{hit['heading'] or 'Document overview'} · effective {hit['effective_from']} · score {hit['score']}")
            st.markdown(f"<div class='bb-quote'>{quote_html(hit['quote'])}</div>", unsafe_allow_html=True)
            if hit.get("source_url"):
                st.caption(f"Source: {hit['source_url']} · {hit['licence']}")
            else:
                st.caption(hit["licence"])


try:
    state = load_business_state()
except StateLoadError as exc:
    st.error(f"Cannot load the synthetic business state: {exc}")
    st.stop()

inference = safe_get("/api/v1/status", None)
parties = safe_get("/api/v1/parties", [])
scenarios = safe_get("/api/v1/scenarios", [])
review_items = safe_get("/api/v1/review/pending", [])
stock_rows = inventory_rows(state)
open_order_rows = order_rows(state)

if st.session_state.get("next_page"):
    st.session_state.navigation = st.session_state.pop("next_page")
st.session_state.setdefault("navigation", "Overview")
st.session_state.setdefault("recommendation_mode", "deterministic")

with st.sidebar:
    st.markdown(
        """
        <div class="bb-brand">
            <div class="bb-brand-mark">BB</div>
            <div><div class="bb-brand-name">BharatBiz</div><div class="bb-brand-sub">Operations console</div></div>
        </div>
        <div class="bb-side-label">Workspace</div>
        """,
        unsafe_allow_html=True,
    )
    page = st.radio("Workspace", PAGES, key="navigation", label_visibility="collapsed")
    st.markdown('<div class="bb-side-label">Simulation state</div>', unsafe_allow_html=True)
    if inference is None:
        inference_text = "<strong>API offline</strong><br>Business data remains available"
        inference_tone = "#f3b4b4"
    elif inference["llm_enabled"]:
        inference_text = f"<strong>LLM extraction on</strong><br>{escape(inference['model'])}<br>Validated output · recommendation mode selected below"
        inference_tone = "#a7e3d5"
    else:
        inference_text = "<strong>Rules extraction</strong><br>No model call during intake"
        inference_tone = "#a7e3d5"
    st.markdown(
        f"<div class='bb-side-status'><span style='color:{inference_tone}'>{inference_text}</span><br><br>"
        f"<strong>As of</strong> {state.as_of:%d %b %Y}<br><span class='bb-code'>{escape(state.state_version)}</span></div>",
        unsafe_allow_html=True,
    )
    st.selectbox(
        "Recommendation mode",
        ["deterministic", "policy_grounded_llm"],
        key="recommendation_mode",
        format_func=lambda value: "Deterministic" if value == "deterministic" else "Policy-grounded LLM",
        help="Choose one mode for scenario runs and incoming operational messages.",
    )
    if inference and st.session_state.recommendation_mode == "policy_grounded_llm":
        if inference.get("decision_llm_enabled"):
            st.caption(f"Decision model: {escape(inference.get('decision_model') or 'configured model')}")
        else:
            st.warning("The policy-grounded LLM is not configured. Configure the existing LLM provider before running it.")
    if st.button("Reset demo", disabled=inference is None, width="stretch"):
        confirm_demo_reset()
    st.caption("Start fresh: clear scenario runs, chats, reviews, retailer history and model traces.")
    st.divider()
    st.caption("Academic synthetic simulation. Recommendations are advisory and require human approval.")
    st.caption("No purchases · payments · stock mutations · outbound messages")

if page == "Overview":
    render_overview(state, review_items, stock_rows, open_order_rows)
elif page == "Inbox":
    render_inbox(parties, scenarios)
elif page == "Scenario lab":
    render_scenario_lab(scenarios)
elif page == "Decision desk":
    render_decision_desk(review_items)
elif page == "Retail desk":
    render_retail_desk(state, get, post, patch, review_items)
elif page == "Operations data":
    render_operations(state, stock_rows, open_order_rows)
elif page == "Evaluation":
    render_evaluation(inference, get, post)
elif page == "LLM observability":
    render_observability(get)
else:
    render_knowledge()
