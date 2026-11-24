from fastapi.testclient import TestClient

from app.main import app
from app.store.ledger import ledger
from app.store.retail import retail_store

client = TestClient(app)


def test_health():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "mode": "mock"}


def test_primary_demo_api(demo_message):
    response = client.post("/api/v1/messages/process", json=demo_message.model_dump(mode="json"))

    assert response.status_code == 200
    result = response.json()
    assert result["selected_plan"]["candidate_id"] == "supplier-SUP-002"
    assert result["verification"]["valid"]


def test_status_reports_inference_mode_without_secrets():
    response = client.get("/api/v1/status")

    assert response.status_code == 200
    body = response.json()
    assert body["llm_enabled"] is False
    assert body["extractor"] == "rules"
    assert body["model"] == ""
    assert "api_key" not in body


def test_party_directory_lists_names_with_internal_ids():
    response = client.get("/api/v1/parties")

    assert response.status_code == 200
    parties = response.json()
    suppliers = {party["party_id"]: party for party in parties if party["party_type"] == "supplier"}
    retailers = {party["party_id"]: party for party in parties if party["party_type"] == "retailer"}
    assert suppliers["SUP-002"]["party_name"] == "Balaji Wholesale Distributors"
    assert retailers["RET-003"]["party_name"] == "Lakshmi Provision Store"
    assert len(suppliers) == 5
    assert len(retailers) == 20


def test_scenario_catalogue_and_non_plan_execution():
    catalogue = client.get("/api/v1/scenarios")
    assert catalogue.status_code == 200
    rows = catalogue.json()
    assert [row["scenario_id"] for row in rows] == [f"SCN-{index:03d}" for index in range(1, 16)]
    assert all(row["demo_outcome"] for row in rows)
    assert len({row["message"]["text"] for row in rows}) == 15
    assert rows[2]["message"] == {
        "text": "Sri Venkateswara FMCG Supply reports a two-day delay for Cooking oil 1 L pouch; revised date is not confirmed.",
        "language": "English",
        "sender_type": "supplier",
        "sender_id": "SUP-005",
    }

    response = client.post("/api/v1/scenarios/SCN-007/run", json={"persist_review": False})
    assert response.status_code == 200
    result = response.json()
    assert result["review_kind"] == "market_signal_review"
    assert result["market_context"]["distinct_reporter_count"] == 2
    assert result["selected_plan"] is None


def test_unknown_scenario_returns_404():
    response = client.post("/api/v1/scenarios/SCN-999/run", json={})
    assert response.status_code == 404


def test_api_rejects_state_version_mismatch(demo_message):
    payload = demo_message.model_dump(mode="json")
    payload["state_version"] = "sim-v1"

    response = client.post("/api/v1/messages/process", json=payload)

    assert response.status_code == 409
    assert "does not match" in response.json()["detail"]


def test_demo_reset_clears_persistent_state_and_allows_a_fresh_replay():
    ledger.reset()
    retail_store.reset()
    try:
        first = client.post("/api/v1/scenarios/SCN-007/run", json={"persist_review": True})
        assert first.status_code == 200
        assert first.json()["inbound"]["duplicate"] is False
        assert ledger.pending_reviews()
        retail_store.persist(
            {
                "event_id": "reset-event",
                "message_id": "reset-message",
                "retailer_id": "RET-001",
                "intent": "delivery_complaint",
                "reporter_id": "RET-001",
                "observed_at": "2026-11-01T09:00:00+05:30",
            }
        )
        assert retail_store.interactions_for("RET-001", "2026-01-01T00:00:00+00:00")
        ledger.open_intake("unfinished-demo", "message-1", "Incomplete message", 1)

        response = client.post("/api/v1/demo/reset")

        assert response.status_code == 200
        assert response.json()["status"] == "reset"
        assert ledger.pending_reviews() == []
        assert ledger.get_intake("unfinished-demo") is None
        assert retail_store.interactions_for("RET-001", "2026-01-01T00:00:00+00:00") == []
        assert retail_store.list_cases() == []
        assert retail_store.list_drafts() == []
        assert len(client.get("/api/v1/scenarios").json()) == 15

        replay = client.post("/api/v1/scenarios/SCN-007/run", json={"persist_review": True})
        assert replay.status_code == 200
        assert replay.json()["inbound"]["duplicate"] is False
    finally:
        ledger.reset()
        retail_store.reset()
