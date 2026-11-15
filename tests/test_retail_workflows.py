from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.orchestration.inbound import process_inbound
from app.orchestration.review_actions import decide_review
from app.orchestration.workflow import process_message
from app.schemas.contracts import MessageSubmission
from app.schemas.retail import CaseProposal, MarketObservation, ResponseDraft
from app.store.ledger import InboundLedger, ReviewDecisionError, ledger
from app.store.retail import RetailStore, retail_store

client = TestClient(app)
STATE_VERSION = "synthetic-v2-seed-20261105"
COMPLAINT = "Cooking oil 5 L tin arrived damaged in ORD-0016."


@pytest.fixture(autouse=True)
def clear_ledger():
    ledger.reset()
    yield
    ledger.reset()


def inbound(text: str, message_id: str, **overrides) -> dict:
    response = client.post(
        "/api/v1/inbound",
        json={
            "text": text,
            "message_id": message_id,
            "sender_type": "retailer",
            "sender_id": "RET-001",
            "language": "English",
            "state_version": STATE_VERSION,
            **overrides,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def message(text: str = COMPLAINT, message_id: str = "retail-1") -> MessageSubmission:
    return MessageSubmission(
        message_id=message_id,
        source_type="retailer_message",
        text=text,
        observed_at="2026-11-02T11:00:00+05:30",
        language="English",
        state_version=STATE_VERSION,
        sender={"party_type": "retailer", "party_id": "RET-001", "channel": "chat"},
    )


def test_repeat_complaint_links_case_and_audits_manual_send():
    first = inbound(COMPLAINT, "case-1")
    second = inbound(COMPLAINT, "case-2")

    case_id = first["result"]["retail_context"]["case_id"]
    assert second["result"]["retail_context"]["case_id"] == case_id
    case = client.get(f"/api/v1/retail/cases/{case_id}").json()
    assert len(case["event_ids"]) == 2
    assert case["priority"] == "high"
    assert any("recurring" in reason for reason in case["activity"][1]["detail"].get("reasons", [])) or any(
        row["kind"] == "priority_raised" for row in case["activity"]
    )

    draft_id = first["result"]["retail_context"]["draft_id"]
    event_id = first["event"]["event_id"]
    assert client.post(f"/api/v1/retail/drafts/{draft_id}/mark-sent", json={"sent_by": "staff"}).status_code == 409
    generic = client.post(f"/api/v1/review/{event_id}", json={"decision": "approve", "reviewer": "staff"})
    assert generic.status_code == 409

    reviewed = client.post(
        f"/api/v1/retail/drafts/{draft_id}/review",
        json={"event_id": event_id, "decision": "approve", "reviewer": "staff"},
    )
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["draft"]["review_status"] == "approved"
    assert client.post(
        f"/api/v1/retail/drafts/{draft_id}/review",
        json={"event_id": event_id, "decision": "reject", "reviewer": "other"},
    ).status_code == 409

    sent = client.post(f"/api/v1/retail/drafts/{draft_id}/mark-sent", json={"sent_by": "staff"})
    assert sent.status_code == 200
    assert sent.json()["sent_manually_by"] == "staff"
    assert client.post(f"/api/v1/retail/drafts/{draft_id}/mark-sent", json={"sent_by": "staff"}).status_code == 409


def test_case_lifecycle_requires_resolution_and_rejects_invalid_transition():
    result = inbound(COMPLAINT, "lifecycle-1")
    case_id = result["result"]["retail_context"]["case_id"]

    missing_note = client.patch(
        f"/api/v1/retail/cases/{case_id}", json={"actor": "staff", "status": "resolved"}
    )
    assert missing_note.status_code == 409
    resolved = client.patch(
        f"/api/v1/retail/cases/{case_id}",
        json={
            "actor": "staff",
            "status": "resolved",
            "owner": "retail-desk",
            "resolution_note": "Delivery evidence checked and retailer contacted manually.",
        },
    )
    assert resolved.status_code == 200
    assert resolved.json()["owner"] == "retail-desk"
    closed = client.patch(f"/api/v1/retail/cases/{case_id}", json={"actor": "staff", "status": "closed"})
    assert closed.status_code == 200
    invalid = client.patch(
        f"/api/v1/retail/cases/{case_id}", json={"actor": "staff", "status": "in_progress"}
    )
    assert invalid.status_code == 409


def test_draft_edit_is_checked_and_concurrent_reviews_decide_once():
    result = inbound(COMPLAINT, "review-race")
    draft_id = result["result"]["retail_context"]["draft_id"]
    event_id = result["event"]["event_id"]

    unsafe = client.post(
        f"/api/v1/retail/drafts/{draft_id}/review",
        json={
            "event_id": event_id,
            "decision": "approve",
            "reviewer": "staff",
            "final_text": "We will refund ₹500 tomorrow.",
        },
    )
    assert unsafe.status_code == 422
    whitespace = client.post(
        f"/api/v1/retail/drafts/{draft_id}/review",
        json={"event_id": event_id, "decision": "approve", "reviewer": "staff", "final_text": "   "},
    )
    assert whitespace.status_code == 422

    def review(reviewer: str):
        return decide_review(
            ledger,
            retail_store,
            event_id,
            "approve",
            reviewer,
            draft_id=draft_id,
            final_text="We have noted your report and our team will contact you.",
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(review, f"staff-{index}") for index in range(2)]
        outcomes = []
        for future in futures:
            try:
                outcomes.append(future.result()["reviewer"])
            except ReviewDecisionError:
                outcomes.append("conflict")
    assert sorted(outcomes) == ["conflict", "staff-0"] or sorted(outcomes) == ["conflict", "staff-1"]
    assert retail_store.get_draft(draft_id)["reviewer"] in {"staff-0", "staff-1"}


def test_product_request_has_indicative_stock_and_safe_request_draft():
    result = inbound(
        "Do you have Toothpaste case availability?",
        "request-1",
        sender_id="RET-004",
    )

    market = result["result"]["market_context"]
    assert market["matched_sku_id"] == "SKU-012"
    assert market["stock_check"]["status"] == "indicative_only"
    assert market["stock_check"]["order_confirmed"] is False
    assert market["stock_check"]["incoming_stock_included"] is False
    draft = retail_store.get_draft(result["result"]["retail_context"]["draft_id"])
    assert draft["kind"] == "request_ack"
    assert draft["review_status"] == "pending_review"
    assert draft["sent_manually_at"] is None


def test_market_corroboration_uses_reporters_and_separates_offers():
    text = "Competitor ValueMart is offering 20 percent off Rice 5 kg bag at a nearby shop in Kukatpally."
    first = inbound(text, "market-1", sender_type="sales_rep", sender_id="REP-017")
    second = inbound(text, "market-2", sender_type="sales_rep", sender_id="REP-018")
    assert first["result"]["market_context"]["corroboration"] == "single_reporter_unverified"
    assert second["result"]["market_context"]["corroboration"] == "corroborated_unverified"
    assert second["result"]["market_context"]["distinct_reporter_count"] == 2

    other_offer = text.replace("20 percent", "10 percent")
    third = inbound(other_offer, "market-3", sender_type="sales_rep", sender_id="REP-019")
    assert third["result"]["market_context"]["corroboration"] == "single_reporter_unverified"
    themes = client.get("/api/v1/retail/market-signals?signal_type=competitor_observation").json()
    assert len(themes) == 2
    assert {theme["distinct_reporters"] for theme in themes} == {1, 2}


def test_missing_reporter_never_fabricates_corroboration():
    text = "Competitor ValueMart is offering 20 percent off Rice 5 kg bag at a nearby shop in Kukatpally."
    inbound(text, "anon-1", sender_type="sales_rep", sender_id=None)
    result = inbound(text, "anon-2", sender_type="sales_rep", sender_id=None)
    assert result["result"]["market_context"]["distinct_reporter_count"] == 0
    assert result["result"]["market_context"]["corroboration"] == "single_reporter_unverified"


def test_unknown_retailer_does_not_open_a_case():
    result = inbound(COMPLAINT, "unknown-retailer", sender_id="RET-999")
    assert result["result"].get("retail_context", {}).get("case_id") is None
    assert retail_store.list_cases() == []
    assert client.get("/api/v1/retail/retailers/RET-999").status_code == 404


def test_slot_questions_duplicates_and_direct_processing_do_not_persist_retail_records():
    question = inbound("An item arrived damaged in my order.", "clarify-1")
    assert question["routed_action"] == "slot_question"
    assert retail_store.list_cases() == []
    assert retail_store.interactions_for("RET-001", "2020-01-01T00:00:00+00:00") == []

    first = inbound(COMPLAINT, "duplicate-retail")
    inbound(COMPLAINT, "duplicate-retail")
    assert len(retail_store.list_cases()[0]["event_ids"]) == 1
    assert len(retail_store.list_drafts()) == 1

    direct = process_message(message("Cooking oil 5 L tin arrived damaged in ORD-0016.", "direct-1"))
    assert direct["case_context"]["clarification_slot"] is None
    assert len(retail_store.list_cases()) == 1
    assert first["duplicate"] is False


def test_failed_retail_persistence_is_not_acknowledged_and_can_be_retried(monkeypatch):
    retry_ledger = InboundLedger()
    with monkeypatch.context() as patch:
        patch.setattr(retail_store, "persist", lambda *args: (_ for _ in ()).throw(RuntimeError("write failed")))
        with pytest.raises(RuntimeError, match="write failed"):
            process_inbound(message(), ledger=retry_ledger)
    assert retry_ledger.get_result("retail-1") is None
    assert retry_ledger.pending_reviews() == []

    result = process_inbound(message(), ledger=retry_ledger)
    assert result["duplicate"] is False
    assert retry_ledger.get_result("retail-1") is not None
    assert len(retail_store.list_cases()) == 1


def test_store_rolls_back_case_draft_and_interaction_when_observation_fails():
    store = RetailStore()
    interaction = {
        "event_id": "evt-atomic",
        "message_id": "msg-atomic",
        "retailer_id": "RET-001",
        "intent": "damaged_item",
        "reporter_id": "RET-001",
        "observed_at": "2026-11-02T11:00:00+05:30",
    }
    case = CaseProposal(
        case_id="case-atomic",
        retailer_id="RET-001",
        category="damaged_item",
        priority="normal",
        summary="summary",
        follow_up="follow up",
    )
    draft = ResponseDraft(
        draft_id="draft-atomic",
        event_id="evt-atomic",
        retailer_id="RET-001",
        language="English",
        kind="complaint_ack",
        text="We have noted your report.",
    )
    invalid = MarketObservation(
        observation_id="obs-atomic",
        event_id="evt-atomic",
        signal_type="product_request",
        subject="Rice",
        observed_at="not-a-time",
        observation_text="text",
        evidence_span="text",
        source_message_id="msg-atomic",
    )
    with pytest.raises(ValueError):
        store.persist(interaction, case, draft, [invalid])
    assert store.get_case("case-atomic") is None
    assert store.get_draft("draft-atomic") is None
    assert store.interactions_for("RET-001", "2020-01-01T00:00:00+00:00") == []
    assert store.observations() == []
