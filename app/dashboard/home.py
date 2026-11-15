import json
import os
import urllib.error
import urllib.request
from decimal import Decimal
from pathlib import Path

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = PROJECT_ROOT / "data" / "synthetic" / "scenario_fixtures" / "SCN-003.json"
API_URL = os.getenv("BHARATBIZ_API_URL", "http://127.0.0.1:8000")


def format_rupees(value: str) -> str:
    return f"₹{Decimal(str(value)):,.2f}"


def inference_note() -> str:
    try:
        with urllib.request.urlopen(f"{API_URL}/api/v1/status", timeout=5) as response:
            status = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, ValueError):
        return "Inference status unavailable — start the API"
    if not status["llm_enabled"]:
        return "LLM inference: OFF — deterministic rules only"
    return f"LLM inference: ON — {status['model']}"


st.set_page_config(page_title="BharatBiz AI — SCN-003", layout="wide")
st.title("BharatBiz AI — Supplier Delay Demo")
st.info(f"Academic synthetic simulation · {inference_note()} · No live integrations or autonomous actions")

fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
message_text = st.text_area("Supplier update", fixture["message"]["text"], height=90)
state_version = st.text_input("State version", fixture["message"]["state_version"])

if st.button("Run SCN-003", type="primary"):
    payload = dict(fixture["message"])
    payload["text"] = message_text
    payload["state_version"] = state_version
    request = urllib.request.Request(
        f"{API_URL}/api/v1/messages/process",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            st.session_state.result = json.loads(response.read().decode("utf-8"))
        st.session_state.review_status = "pending_review"
    except urllib.error.HTTPError as exc:
        st.session_state.result = None
        st.error(f"API returned {exc.code}: {exc.read().decode('utf-8')}")
    except urllib.error.URLError as exc:
        st.session_state.result = None
        st.error(f"Cannot reach the API at {API_URL}. Start Uvicorn before running the demo: {exc.reason}")

result = st.session_state.get("result")
if not result:
    st.caption("Start the FastAPI server, then select Run SCN-003.")
    st.stop()

event = result["event"]
recommendation = result["recommendation"]
st.caption(f"Mode: {result['mode']} · Event: {event['event_id']} · State: {event['state_version']}")

st.subheader("1. Evidence-linked event")
st.write(f"**Event type:** {event['event_type']}")
if event["extracted_facts"]:
    st.dataframe(
        [
            {
                "Field": fact["field"],
                "Value": fact["value"],
                "Exact evidence": fact["evidence_span"],
                "Offsets": f"{fact['span_start']}–{fact['span_end']}",
            }
            for fact in event["extracted_facts"]
        ],
        use_container_width=True,
        hide_index=True,
    )
st.write("**Catalogue and scenario inferences**")
st.json(event["inferences"])
for uncertainty in event["uncertainties"]:
    st.warning(uncertainty)

selected = result.get("selected_plan")
if not selected:
    st.error(recommendation["summary"])
    st.stop()

inventory = result["agent_results"][0]["proposal"]
orders = result["agent_results"][1]["proposal"]
st.subheader("2. Operational impact")
columns = st.columns(5)
columns[0].metric("On hand", f"{inventory['on_hand_units']} {inventory['unit']}")
columns[1].metric("Reserved", f"{inventory['reserved_units']} {inventory['unit']}")
columns[2].metric("Delayed incoming", f"{inventory['delayed_incoming_units']} {inventory['unit']}")
columns[3].metric("ATP (before delay)", f"{inventory['atp_units']} {inventory['unit']}")
columns[4].metric("Immediately usable", f"{inventory['immediately_available_units']} {inventory['unit']}")
st.write(f"**{orders['affected_order_count']} affected orders · {orders['total_requested_units']} {orders['unit']} requested**")
st.dataframe(
    [
        {
            "Order": row["order_id"],
            "Retailer": row.get("retailer_name") or row["retailer_id"],
            "Area": row.get("area", ""),
            "Retailer ID": row["retailer_id"],
            "Requested date": row["requested_delivery_date"],
            "Quantity": row["quantity_units"],
            "Priority": row["priority"],
        }
        for row in orders["affected_orders"]
    ],
    use_container_width=True,
    hide_index=True,
)

st.subheader("3. Supplier and cash alternatives")
st.dataframe(
    [
        {
            "Supplier": option.get("supplier_name") or option["supplier_id"],
            "Supplier ID": option["supplier_id"],
            "Quantity": option["quantity_units"],
            "Unit cost": format_rupees(option["unit_cost_rupees"]),
            "Total cost": format_rupees(option["total_cost_rupees"]),
            "Lead days": option["lead_time_days"],
            "Scenario arrival": option["scenario_arrival_date"],
            "Feasible": option["feasible"],
            "Limitations": ", ".join(option["reasons"]),
        }
        for option in result["supplier_options"]
    ],
    use_container_width=True,
    hide_index=True,
)
st.caption("Scenario arrivals are planning estimates, not supplier-confirmed commitments. Costs use exact decimal rupees.")

st.subheader("4. Selected deterministic plan")
columns = st.columns(5)
columns[0].metric("Candidate", selected["candidate_id"])
columns[1].metric("Fulfilled", selected["fulfilled_units"])
columns[2].metric("Late", selected["late_units"])
columns[3].metric("Unmet", selected["unmet_units"])
columns[4].metric("Cost", format_rupees(selected["total_cost_rupees"]))
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
        for row in selected["allocations"]
    ],
    use_container_width=True,
    hide_index=True,
)
cash = selected["cash_projection"]
st.write(
    f"**Ending cash:** {format_rupees(cash['ending_cash_rupees'])} · "
    f"**Minimum buffer:** {format_rupees(cash['minimum_buffer_rupees'])} · "
    f"**Headroom:** {format_rupees(cash['headroom_rupees'])}"
)

st.subheader("5. Independent verification")
verification = result["verification"]
if verification["valid"]:
    st.success("All stock, allocation, supplier, arrival, cost, cash, and state-version checks passed.")
else:
    st.error("Verification failed")
    st.write(verification["violations"])

st.subheader("6. Human review")
st.write(recommendation["summary"])
st.write("**Assumptions**")
for assumption in recommendation["assumptions"]:
    st.write(f"- {assumption}")
for warning in recommendation["warnings"]:
    st.warning(warning)

approve, reject = st.columns(2)
if approve.button("Approve recommendation"):
    st.session_state.review_status = "approved"
if reject.button("Reject recommendation"):
    st.session_state.review_status = "rejected"
review_status = st.session_state.get("review_status", recommendation["review_status"])
st.write(f"**Review status:** `{review_status}`")
st.caption("Review changes demo session state only. No purchase, payment, stock update, or outbound message is executed.")
