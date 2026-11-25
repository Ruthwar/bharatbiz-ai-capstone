import urllib.error
import urllib.parse

import streamlit as st

from app.dashboard.theme import badge, empty_state, metric_card, page_header, section_title


def _get(get, path: str, fallback):
    try:
        return get(path)
    except (urllib.error.URLError, TimeoutError, ValueError):
        return fallback


def _show_error(exc: Exception) -> None:
    if isinstance(exc, urllib.error.HTTPError):
        st.error(f"API returned {exc.code}: {exc.read().decode('utf-8')}")
    else:
        st.error(f"Retail API request failed: {exc}")


def _fulfilment(state, get) -> None:
    section_title(
        "Priority fulfilment view",
        "An additive allocation analysis; it does not change SCN-003's first-come planner or mutate stock.",
    )
    sku_column, incoming_column = st.columns([2, 1])
    sku = sku_column.selectbox(
        "Product",
        [None] + [row["sku_id"] for row in state.products],
        format_func=lambda value: value or "All products",
    )
    include_incoming = incoming_column.checkbox("Include unverified incoming stock", value=False)
    query = urllib.parse.urlencode({"include_incoming": str(include_incoming).lower(), **({"sku_id": sku} if sku else {})})
    result = _get(get, f"/api/v1/retail/fulfilment?{query}", None)
    if result is None:
        empty_state("Fulfilment unavailable", "Start the API to calculate the priority allocation view.")
        return
    columns = st.columns(4)
    with columns[0]:
        metric_card("Order lines", str(len(result["allocations"])))
    with columns[1]:
        metric_card("Overall fill rate", f"{result['fill_rate']:.1%}")
    with columns[2]:
        metric_card("Changed vs FIFO", str(len(result["changed_vs_fifo"])), "Priority view only")
    with columns[3]:
        metric_card(
            "Verification",
            "Passed" if not result["verification_violations"] else "Failed",
            f"{len(result['verification_violations'])} violations",
            "success" if not result["verification_violations"] else "danger",
        )
    st.caption("Service order: " + result["rule"] + ". Incoming stock is excluded unless explicitly selected.")
    st.dataframe(
        [
            {
                "Order": row["order_id"],
                "Retailer": row["retailer_name"] or row["retailer_id"],
                "SKU": row["sku_id"],
                "Priority": row["priority"],
                "Due": row["requested_delivery_date"],
                "Requested": row["requested_units"],
                "Allocated": row["allocated_units"],
                "Unmet": row["unmet_units"],
                "Unit": row["unit"],
                "Status": row["status"],
            }
            for row in result["allocations"]
        ],
        width="stretch",
        hide_index=True,
    )
    for violation in result["verification_violations"]:
        st.error(violation)
    if result["changed_vs_fifo"]:
        with st.expander("Compare with first-come allocation"):
            st.dataframe(result["changed_vs_fifo"], width="stretch", hide_index=True)


def _cases(get, patch) -> None:
    section_title("Retailer cases", "Repeat reports link by retailer, issue category and product; every transition is audited.")
    status = st.selectbox(
        "Case status",
        [None, "open", "in_progress", "waiting_for_information", "resolved", "closed"],
        format_func=lambda value: value.replace("_", " ").title() if value else "All statuses",
    )
    rows = _get(get, "/api/v1/retail/cases" + (f"?status={status}" if status else ""), [])
    if not rows:
        empty_state("No cases in this view", "Resolved retailer complaints from channel intake will appear here.")
        return
    st.dataframe(
        [
            {
                "Case": row["case_id"],
                "Retailer": row["retailer_id"],
                "Issue": row["category"],
                "SKU": row["sku_id"],
                "Priority": row["priority"],
                "Status": row["status"],
                "Reports": len(row["event_ids"]),
                "Owner": row["owner"] or "Unassigned",
            }
            for row in rows
        ],
        width="stretch",
        hide_index=True,
    )
    selected_id = st.selectbox("Case workspace", [row["case_id"] for row in rows])
    selected = _get(get, f"/api/v1/retail/cases/{selected_id}", None)
    if not selected:
        return
    st.write(selected["summary"])
    st.caption(f"Follow-up: {selected['follow_up']} · orders: {', '.join(selected['order_ids']) or 'none'}")
    with st.form(f"case-update-{selected_id}"):
        actor = st.text_input("Staff ID", "ops-owner")
        owner = st.text_input("Owner", selected["owner"] or "")
        next_status = st.selectbox(
            "New status",
            [selected["status"], "open", "in_progress", "waiting_for_information", "resolved", "closed"],
        )
        note = st.text_area("Activity note")
        resolution = st.text_area("Resolution note (required to resolve)", selected["resolution_note"] or "")
        submitted = st.form_submit_button("Save case update", type="primary")
    if submitted:
        try:
            patch(
                f"/api/v1/retail/cases/{selected_id}",
                {
                    "actor": actor,
                    "status": next_status,
                    "owner": owner or None,
                    "note": note or None,
                    "resolution_note": resolution or None,
                },
            )
        except (urllib.error.URLError, TimeoutError) as exc:
            _show_error(exc)
        else:
            st.toast("Case updated; no operational action was executed.")
            st.rerun()
    with st.expander("Case activity", expanded=True):
        st.dataframe(
            [
                {
                    "At": row["at"],
                    "Actor": row["actor"],
                    "Activity": row["kind"],
                    "Detail": str(row["detail"]),
                }
                for row in selected["activity"]
            ],
            width="stretch",
            hide_index=True,
        )


def _drafts(get, post, review_items: list[dict]) -> None:
    section_title(
        "Retailer reply drafts",
        "English, Hinglish and Hindi drafts need human approval. Marking sent records a manual action; it never sends.",
    )
    rows = _get(get, "/api/v1/retail/drafts", [])
    if not rows:
        empty_state("No reply drafts", "Completed complaint and product-request intake will create safe drafts here.")
        return
    st.dataframe(
        [
            {
                "Draft": row["draft_id"],
                "Retailer": row["retailer_id"],
                "Language": row["language"],
                "Kind": row["kind"],
                "Review": row["review_status"],
                "Manually sent": row["sent_manually_at"] or "No",
            }
            for row in rows
        ],
        width="stretch",
        hide_index=True,
    )
    selected_id = st.selectbox("Draft workspace", [row["draft_id"] for row in rows])
    draft = next(row for row in rows if row["draft_id"] == selected_id)
    st.markdown(f"{badge(draft['review_status'], 'warning' if draft['review_status'] == 'pending_review' else 'neutral')}")
    review = next((item for item in review_items if item.get("draft_id") == selected_id), None)
    if review:
        with st.form(f"draft-review-{selected_id}"):
            final_text = st.text_area("Approved reply text", draft["final_text"] or draft["text"], height=130)
            reviewer = st.text_input("Reviewer ID", "ops-owner")
            note = st.text_input("Review note")
            approve, reject = st.columns(2)
            approved = approve.form_submit_button("Approve reply", type="primary", width="stretch")
            rejected = reject.form_submit_button("Reject reply", width="stretch")
        if approved or rejected:
            try:
                post(
                    f"/api/v1/retail/drafts/{selected_id}/review",
                    {
                        "event_id": review["event_id"],
                        "decision": "approve" if approved else "reject",
                        "reviewer": reviewer,
                        "note": note or None,
                        "final_text": final_text,
                    },
                )
            except (urllib.error.URLError, TimeoutError) as exc:
                _show_error(exc)
            else:
                st.toast("Reply review saved. No message was sent and no case was resolved.")
                st.rerun()
    else:
        st.text_area("Reply text", draft["final_text"] or draft["text"], height=130, disabled=True)
    if draft["edit_warnings"]:
        st.warning("Edit checks: " + ", ".join(draft["edit_warnings"]))
    if draft["review_status"] == "approved" and not draft["sent_manually_at"]:
        sent_by = st.text_input("Manual sender ID", "ops-owner", key=f"sender-{selected_id}")
        if st.button("Mark as manually sent", key=f"mark-sent-{selected_id}"):
            try:
                post(f"/api/v1/retail/drafts/{selected_id}/mark-sent", {"sent_by": sent_by})
            except (urllib.error.URLError, TimeoutError) as exc:
                _show_error(exc)
            else:
                st.toast("Manual send recorded for audit; BharatBiz did not send the message.")
                st.rerun()
    if draft["sent_manually_at"]:
        st.success(f"Manually sent by {draft['sent_manually_by']} at {draft['sent_manually_at']} (audit mark only).")


def _market(get) -> None:
    section_title(
        "Market observations",
        "Corroboration counts distinct stable reporters within the same competitor, product, offer and area.",
    )
    signal = st.selectbox(
        "Signal type",
        [None, "competitor_observation", "pack_size_request", "product_request"],
        format_func=lambda value: value.replace("_", " ").title() if value else "All signals",
    )
    minimum = st.number_input("Minimum distinct reporters", min_value=1, value=1, step=1)
    query = urllib.parse.urlencode({"min_reporters": minimum, **({"signal_type": signal} if signal else {})})
    rows = _get(get, f"/api/v1/retail/market-signals?{query}", [])
    if not rows:
        empty_state("No matching observations", "Signals remain reported and unverified until staff investigate them.")
        return
    st.dataframe(
        [
            {
                "Signal": row["signal_type"],
                "Subject": row["subject"],
                "Product": row["product_label"],
                "Offer": row["offer"],
                "Area": row["area"],
                "Reports": row["report_count"],
                "Reporters": row["distinct_reporters"],
                "Status": row["label"],
                "Last seen": row["last_seen"],
            }
            for row in rows
        ],
        width="stretch",
        hide_index=True,
    )
    st.warning("No price, procurement, supplier-availability or assortment action is inferred from these reports.")


def _retailer(state, get) -> None:
    section_title("Retailer 360", "Order history, priority allocation, open cases and recurring issues in one workspace.")
    retailer_id = st.selectbox(
        "Retailer",
        [row["retailer_id"] for row in state.retailers],
        format_func=lambda value: next(
            f"{row['retailer_name']} · {value}" for row in state.retailers if row["retailer_id"] == value
        ),
    )
    overview = _get(get, f"/api/v1/retail/retailers/{retailer_id}", None)
    if not overview:
        empty_state("Retailer overview unavailable", "Start the API to load the retailer workspace.")
        return
    record = overview["retailer"]
    columns = st.columns(4)
    with columns[0]:
        metric_card("Service priority", record["service_priority"].title(), record["area"])
    with columns[1]:
        metric_card("Historical orders", str(overview["history"].get("orders", 0)))
    with columns[2]:
        metric_card("Open order lines", str(len(overview["open_orders"])))
    with columns[3]:
        metric_card("Cases", str(len(overview["cases"])))
    if overview["recurring_issues"]:
        st.warning("Recurring issues: " + ", ".join(
            f"{row['intent'].replace('_', ' ')} × {row['count']}" for row in overview["recurring_issues"]
        ))
    st.dataframe(overview["open_orders"], width="stretch", hide_index=True)


def render_retail_desk(state, get, post, patch, review_items: list[dict]) -> None:
    cases = _get(get, "/api/v1/retail/cases", [])
    drafts = _get(get, "/api/v1/retail/drafts", [])
    open_cases = [row for row in cases if row["status"] in {"open", "in_progress", "waiting_for_information"}]
    pending_drafts = [row for row in drafts if row["review_status"] == "pending_review"]
    page_header(
        "Retailer operations",
        "Retail desk",
        "Prioritise fulfilment, investigate repeat complaints, approve safe replies and review reported market evidence.",
        f"{len(open_cases)} active cases · {len(pending_drafts)} drafts awaiting review",
    )
    fulfilment_tab, cases_tab, drafts_tab, market_tab, retailer_tab = st.tabs(
        ["Fulfilment", "Cases", "Reply drafts", "Market signals", "Retailer 360"]
    )
    with fulfilment_tab:
        _fulfilment(state, get)
    with cases_tab:
        _cases(get, patch)
    with drafts_tab:
        _drafts(get, post, review_items)
    with market_tab:
        _market(get)
    with retailer_tab:
        _retailer(state, get)
