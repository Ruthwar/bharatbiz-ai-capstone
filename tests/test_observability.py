import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.decision import selector
from app.decision.selector import _post_completion
from app.main import app
from app.observability import reset_traces, trace_scope, trace_store
from app.observability.export import export_settings, export_span
from app.observability import record_span
from app.orchestration.workflow import _extract
from app.rag.retrieval import retrieve
from app.scenarios.service import run_scenario
from app.store.ledger import ledger

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_traces():
    reset_traces()
    ledger.reset()
    yield
    reset_traces()
    ledger.reset()


@pytest.fixture
def llm_env(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_BASE_URL", "https://gateway.invalid/v1")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_MODEL", "stub-model")


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class _FakeClient:
    payload: dict = {}
    error: Exception | None = None

    def __init__(self, **kwargs) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def post(self, *args, **kwargs):
        if _FakeClient.error is not None:
            raise _FakeClient.error
        return _FakeResponse(_FakeClient.payload)


def test_scope_groups_and_summarises_spans():
    with trace_scope("scenario:SCN-003", scenario_id="SCN-003", source="scenario"):
        retrieve("supplier delay policy", top_k=2)
        record_span(
            "decision_plan",
            "generation",
            provider="openai-compatible",
            model="stub-model",
            prompt_version="policy-decision-v2",
            latency_ms=120,
            prompt_tokens=10,
            completion_tokens=4,
            detail={"selection": "supplier-SUP-002"},
        )

    summary = trace_store.summary()
    assert summary["totals"]["spans"] == 2
    assert summary["totals"]["generations"] == 1
    assert summary["totals"]["retrieval_calls"] == 1
    assert summary["tokens"] == {"prompt": 10, "completion": 4, "total": 14}
    assert summary["latency_ms"]["p50"] == 120.0
    runs = summary["runs"]
    assert len(runs) == 1
    assert runs[0]["scenario_id"] == "SCN-003"
    assert runs[0]["session"] == "scenario:SCN-003"
    assert runs[0]["steps"] == ["retrieval", "decision_plan"]
    assert summary["cost"]["estimated"] is None
    assert summary["cost"]["basis"] == "not priced"
    assert summary["database"] == ":memory:"


def test_retrieval_outside_a_scope_is_not_recorded():
    retrieve("supplier delay policy", top_k=1)

    assert trace_store.spans() == []


def test_selector_success_records_generation_with_usage(llm_env, monkeypatch):
    _FakeClient.error = None
    _FakeClient.payload = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "candidate_id": "supplier-SUP-002",
                            "priority": "service",
                            "citations": ["POL-DLY-001"],
                        }
                    )
                }
            }
        ],
        "usage": {"prompt_tokens": 321, "completion_tokens": 45},
    }
    monkeypatch.setattr(selector.httpx, "Client", _FakeClient)

    with trace_scope("scenario:SCN-003", scenario_id="SCN-003", source="scenario"):
        parsed, model, latency = _post_completion(
            "system",
            {"event": {"event_type": "supplier_delay"}},
            200,
            step="decision_plan",
            prompt_version="policy-decision-v2",
            detail={"event_type": "supplier_delay", "candidates": 3},
        )

    assert parsed["candidate_id"] == "supplier-SUP-002"
    assert model == "stub-model"
    spans = trace_store.spans()
    assert len(spans) == 1
    span = spans[0]
    assert span["step"] == "decision_plan"
    assert span["kind"] == "generation"
    assert span["model"] == "stub-model"
    assert span["prompt_version"] == "policy-decision-v2"
    assert span["prompt_tokens"] == 321
    assert span["completion_tokens"] == 45
    assert span["status"] == "ok"
    assert span["detail"]["selection"] == "supplier-SUP-002"
    assert span["detail"]["candidates"] == 3


def test_selector_failure_records_error_span(llm_env, monkeypatch):
    _FakeClient.error = httpx.ConnectError("gateway unreachable")
    monkeypatch.setattr(selector.httpx, "Client", _FakeClient)

    with trace_scope("message:MSG-1", source="message"):
        with pytest.raises(Exception, match="Policy-grounded LLM request failed"):
            _post_completion(
                "system", {"event": {}}, 200, step="decision_review", prompt_version="policy-review-v1"
            )

    span = trace_store.spans()[0]
    assert span["status"] == "error"
    assert span["error"] == "ConnectError"
    assert span["step"] == "decision_review"


def test_unconfigured_decision_mode_is_traced_as_an_error():
    with trace_scope("message:MSG-1", source="message"):
        with pytest.raises(Exception, match="not configured"):
            _post_completion("system", {}, 200, step="decision_plan", prompt_version="policy-decision-v2")

    span = trace_store.spans()[0]
    assert span["status"] == "error"
    assert "not configured" in span["error"]


class _FailingExtractor:
    name = "llm"
    model = "stub-model"

    def extract(self, message, state):
        raise RuntimeError("model returned unparseable JSON")


def test_extraction_fallback_is_traced(demo_message, state):
    with trace_scope("message:MSG-1", source="message"):
        extraction = _extract(demo_message, state, _FailingExtractor())

    assert extraction.mode == "rules_mock"
    span = trace_store.spans()[0]
    assert span["kind"] == "fallback"
    assert span["step"] == "extraction_fallback"
    assert span["status"] == "fallback"
    assert span["detail"]["reason"] == "RuntimeError"


def test_scenario_run_groups_retrieval_spans_under_the_scenario():
    run_scenario("SCN-010", persist=True)

    spans = trace_store.spans()
    assert spans
    assert {span["session"] for span in spans} == {"scenario:SCN-010"}
    assert {span["scenario_id"] for span in spans} == {"SCN-010"}
    assert {span["kind"] for span in spans} == {"retrieval"}
    runs = trace_store.summary()["runs"]
    assert runs[0]["scenario_id"] == "SCN-010"
    assert runs[0]["steps"] == ["retrieval"]


def test_observability_api_reports_totals_and_export_state():
    response = client.post(
        "/api/v1/scenarios/SCN-010/run", json={"persist_review": True, "decision_mode": "deterministic"}
    )
    assert response.status_code == 200

    response = client.get("/api/v1/observability")
    assert response.status_code == 200
    body = response.json()
    assert body["totals"]["retrieval_calls"] > 0
    assert body["export"]["enabled"] is False
    assert body["database"] == ":memory:"
    trace_id = body["runs"][0]["trace_id"]
    assert body["recent"][0]["trace_id"] == trace_id

    detail = client.get(f"/api/v1/observability/traces/{trace_id}")
    assert detail.status_code == 200
    assert len(detail.json()["spans"]) == body["runs"][0]["spans"]
    assert client.get("/api/v1/observability/traces/trace-unknown").status_code == 404


def test_demo_reset_clears_traces():
    run_scenario("SCN-010", persist=True)
    assert trace_store.spans()

    response = client.post("/api/v1/demo/reset", json={})

    assert response.status_code == 200
    assert "llm_traces" in response.json()["cleared"]
    assert trace_store.spans() == []


def test_export_is_off_by_default():
    assert export_settings()["enabled"] is False
    with trace_scope("scenario:SCN-003", scenario_id="SCN-003"):
        retrieve("supplier delay policy", top_k=1)
    span = trace_store.spans()[0]

    assert export_span(span) is False
    assert trace_store.summary()["totals"]["exported"] == 0


def test_export_builds_langfuse_batch(monkeypatch):
    with trace_scope("scenario:SCN-003", scenario_id="SCN-003"):
        retrieve("supplier delay policy", top_k=1)
        record_span(
            "decision_plan",
            "generation",
            provider="openai-compatible",
            model="stub-model",
            prompt_version="policy-decision-v2",
            latency_ms=80,
            prompt_tokens=12,
            completion_tokens=3,
            detail={"selection": "supplier-SUP-002"},
        )
    generation = next(span for span in trace_store.spans() if span["kind"] == "generation")
    assert generation["exported"] is False

    monkeypatch.setenv("BHARATBIZ_TRACE_EXPORT", "langfuse")
    monkeypatch.setenv("LANGFUSE_HOST", "https://langfuse.invalid")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
    batches: list[list[dict]] = []
    monkeypatch.setattr(
        "app.observability.export._post_batch", lambda events: batches.append(events)
    )

    assert export_span(generation, background=False) is True
    assert len(batches) == 1
    types = [event["type"] for event in batches[0]]
    assert types == ["trace-create", "generation-create"]
    assert batches[0][0]["body"]["id"] == generation["trace_id"]
    assert batches[0][1]["body"]["traceId"] == generation["trace_id"]
    assert batches[0][1]["body"]["usage"] == {"input": 12, "output": 3}
    assert batches[0][1]["body"]["metadata"]["prompt_version"] == "policy-decision-v2"
    assert trace_store.summary()["totals"]["exported"] == 1
