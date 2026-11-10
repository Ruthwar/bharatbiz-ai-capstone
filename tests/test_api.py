from fastapi.testclient import TestClient

from app.main import app

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


def test_api_rejects_state_version_mismatch(demo_message):
    payload = demo_message.model_dump(mode="json")
    payload["state_version"] = "sim-v1"

    response = client.post("/api/v1/messages/process", json=payload)

    assert response.status_code == 409
    assert "does not match" in response.json()["detail"]
