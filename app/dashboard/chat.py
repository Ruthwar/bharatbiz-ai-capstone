import json
import os
import urllib.error
import urllib.request

import streamlit as st

API_URL = os.getenv("BHARATBIZ_API_URL", "http://127.0.0.1:8000")

st.set_page_config(page_title="BharatBiz AI — Intake", layout="wide")
st.title("BharatBiz AI — Message intake")
st.info("Academic synthetic simulation · Receipt is acknowledged · No action executes without human approval")


def post(path: str, payload: dict) -> dict:
    request = urllib.request.Request(
        f"{API_URL}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def get(path: str) -> list[dict]:
    with urllib.request.urlopen(f"{API_URL}{path}", timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


try:
    inference = get("/api/v1/status")
except urllib.error.URLError as exc:
    inference = None
    st.warning(f"Cannot read the inference status from {API_URL}: {exc.reason}")

if inference:
    if inference["llm_enabled"]:
        st.info(
            f"LLM inference: ON · {inference['model']} ({inference['provider']}). "
            "Model output is validated; planning and decisions stay deterministic and human-approved."
        )
    else:
        st.info("LLM inference: OFF · deterministic rules only; no model is called during intake.")


def render_result(result: dict) -> None:
    event = result.get("event")
    if result.get("processing_error"):
        st.error(f"Processing error: {result['processing_error']} — queued for human review.")
    st.caption(
        f"Routed: `{result['routed_action']}` · Mode: `{result['mode']}` · Rounds: {result['rounds']}"
    )
    if result.get("question"):
        st.info(f"Question asked: {result['question']}")
    if event:
        st.subheader("Evidence-linked event")
        st.write(f"**Intent:** {event['event_type']} · **Status:** {event['status']}")
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
        for uncertainty in event["uncertainties"]:
            st.warning(uncertainty)
        if result.get("recommendation"):
            st.subheader("Recommendation (pending human review)")
            st.write(result["recommendation"]["summary"])


intake_tab, review_tab = st.tabs(["Intake", "Review queue"])

with intake_tab:
    st.caption("Demo channel only: a real channel derives the sender from the authenticated account.")
    try:
        parties = get("/api/v1/parties")
    except urllib.error.URLError as exc:
        parties = []
        st.warning(f"Cannot load the synthetic party directory from {API_URL}: {exc.reason}")

    column1, column2 = st.columns([2, 1])
    if parties:
        labels = {
            f"{party['party_name']} ({party['party_type']}, {party['party_id']})": party
            for party in parties
        }
        sender = labels[column1.selectbox("Sender", list(labels))]
        sender_type, sender_id = sender["party_type"], sender["party_id"]
        column1.caption(f"Internal account ID sent to the API: `{sender_id}`")
    else:
        sender_type = column1.selectbox("Sender", ["retailer", "supplier", "sales_rep", "unknown"])
        sender_id = column1.text_input("Sender account ID (internal)", "SUP-005")
    language = column2.selectbox("Language", ["English", "Hinglish", "Hindi"])
    conversation_id = st.text_input("Conversation", "demo-conversation-1")

    history = st.session_state.setdefault("chat", [])

    text = st.chat_input("Write a message")
    if text:
        payload = {
            "text": text,
            "sender_type": sender_type,
            "sender_id": sender_id,
            "language": language,
            "conversation_id": conversation_id,
        }
        try:
            result = post("/api/v1/inbound", payload)
        except urllib.error.HTTPError as exc:
            st.error(f"API returned {exc.code}: {exc.read().decode('utf-8')}")
        except urllib.error.URLError as exc:
            st.error(f"Cannot reach the API at {API_URL}. Start Uvicorn first: {exc.reason}")
        else:
            history.append({"role": "user", "text": text})
            for ack in (result["ack"], result.get("completion_ack")):
                if ack:
                    history.append({"role": "assistant", "text": ack["text"], "kind": ack["kind"]})
            if result.get("question"):
                history.append({"role": "assistant", "text": result["question"], "kind": "question"})
            st.session_state.last_result = result

    for entry in history:
        with st.chat_message(entry["role"]):
            st.write(entry["text"])
            if entry.get("kind"):
                st.caption(entry["kind"])

    if st.session_state.get("last_result"):
        st.divider()
        render_result(st.session_state.last_result)

with review_tab:
    st.subheader("Pending human review")
    if st.button("Refresh"):
        st.rerun()
    try:
        items = get("/api/v1/review/pending")
    except urllib.error.URLError as exc:
        st.error(f"Cannot reach the API at {API_URL}: {exc.reason}")
        items = []
    if not items:
        st.success("Nothing waiting for review.")
    for index, item in enumerate(items):
        with st.container(border=True):
            st.write(f"**{item['event_type']}** · `{item['routed_action']}` · {item['mode']}")
            st.write(item["summary"])
            approve, reject, _ = st.columns([1, 1, 4])
            if approve.button("Approve", key=f"approve-{index}"):
                post(f"/api/v1/review/{item['event_id']}", {"decision": "approve", "reviewer": "demo-owner"})
                st.rerun()
            if reject.button("Reject", key=f"reject-{index}"):
                post(f"/api/v1/review/{item['event_id']}", {"decision": "reject", "reviewer": "demo-owner"})
                st.rerun()
    st.caption("Decisions update the demo session only. No purchase, payment, stock update or outbound message is executed.")
