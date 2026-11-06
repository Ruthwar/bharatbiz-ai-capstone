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


def test_api_rejects_state_version_mismatch(demo_message):
    payload = demo_message.model_dump(mode="json")
    payload["state_version"] = "sim-v1"

    response = client.post("/api/v1/messages/process", json=payload)

    assert response.status_code == 409
    assert "does not match" in response.json()["detail"]
