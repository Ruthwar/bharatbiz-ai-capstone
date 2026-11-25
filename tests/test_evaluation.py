import time

from fastapi.testclient import TestClient

from app.evaluation.extraction import load_held_out_records, run_extraction_evaluation
from app.evaluation.rag import run_rag_evaluation
from app.evaluation.service import EvaluationJobManager
from app.extraction.base import Extraction
from app.main import app
from app.schemas.contracts import EvidenceFact, IntentMatch

client = TestClient(app)


class SuccessfulLLM:
    name = "llm"
    model = "test-model"

    def extract(self, message, state):
        return Extraction(
            intents=[IntentMatch(intent="supplier_delay", confidence=0.95, evidence_span="delivery is delayed")],
            facts=[
                EvidenceFact(field="product", value="rice", evidence_span="rice"),
                EvidenceFact(
                    field="supplier_name",
                    value="Krishna Rice Mills",
                    evidence_span="Krishna Rice Mills",
                ),
            ],
            mode="llm",
        )


class FailingLLM:
    name = "llm"
    model = "test-model"

    def extract(self, message, state):
        raise RuntimeError("synthetic gateway failure")


def test_rag_evaluation_returns_real_rows_and_progress():
    events = []
    result = run_rag_evaluation(progress=events.append)

    assert result["summary"]["queries"] == 40
    assert result["summary"]["recall_at_3"] == 1.0
    citations = result["summary"]["citation_coverage"]
    assert citations["references"] == 6
    assert citations["with_quote"] == 6
    assert citations["effective_by_scenario_date"] == 6
    assert len(result["rows"]) == 40
    assert all(row["query"] and row["hits"] and row["latency_ms"] >= 0 for row in result["rows"])
    assert sum(event["step"] == "query_completed" for event in events) == 40
    assert events[-1]["step"] == "metrics_completed"


def test_extraction_evaluation_scores_validated_model_output():
    record = next(row for row in load_held_out_records() if row["message_id"] == "HOLD-0006")
    result = run_extraction_evaluation(llm_extractor=SuccessfulLLM(), records=[record])

    metrics = result["summary"]["variants"]["llm"]
    outcome = result["rows"][0]["results"]["llm"]
    assert metrics["intent_accuracy"] == 1.0
    assert metrics["entity_exact_match"] == 1.0
    assert metrics["stated_entity_accuracy"] == 1.0
    assert metrics["record_exact_match"] == 1.0
    assert metrics["verbatim_evidence_rate"] == 1.0
    assert metrics["fallback_count"] == 0
    assert metrics["latency_ms_p95"] >= metrics["latency_ms_p50"]
    assert outcome["predicted_entities"]["supplier_id"] == "SUP-003"


def test_extraction_evaluation_exposes_fallback_and_failure():
    record = load_held_out_records()[0]
    result = run_extraction_evaluation(llm_extractor=FailingLLM(), records=[record])

    outcome = result["rows"][0]["results"]["llm"]
    assert result["summary"]["variants"]["llm"]["fallback_count"] == 1
    assert outcome["fallback"] is True
    assert outcome["validation_passed"] is False
    assert "synthetic gateway failure" in outcome["error"]
    assert outcome["predicted_intent"] == result["rows"][0]["results"]["rules"]["predicted_intent"]


def test_job_manager_records_progress_and_latest_result(monkeypatch):
    def fake_runner(progress):
        progress({"step": "dataset_loaded", "title": "Loaded one query", "current": 0, "total": 1})
        row = {"id": "Q-1"}
        progress(
            {
                "step": "query_completed",
                "title": "Q-1 passed",
                "current": 1,
                "total": 1,
                "row": row,
            }
        )
        return {"summary": {"queries": 1}, "rows": [row]}

    monkeypatch.setattr("app.evaluation.service.run_rag_evaluation", fake_runner)
    manager = EvaluationJobManager()
    started = manager.start("rag")
    deadline = time.monotonic() + 2
    while manager.get(started["job_id"])["status"] in {"queued", "running"}:
        assert time.monotonic() < deadline
        time.sleep(0.01)

    completed = manager.get(started["job_id"])
    assert completed["status"] == "completed"
    assert completed["current"] == 1
    assert completed["rows"] == [{"id": "Q-1"}]
    assert [activity["step"] for activity in completed["activities"]] == ["dataset_loaded", "query_completed"]
    assert manager.latest()["rag"]["job_id"] == started["job_id"]


def test_evaluation_api_runs_rag_and_rejects_disabled_llm():
    started = client.post("/api/v1/evaluations/rag/run")
    assert started.status_code == 202
    job_id = started.json()["job_id"]
    deadline = time.monotonic() + 10
    while True:
        response = client.get(f"/api/v1/evaluations/{job_id}")
        assert response.status_code == 200
        job = response.json()
        if job["status"] not in {"queued", "running"}:
            break
        assert time.monotonic() < deadline
        time.sleep(0.02)

    assert job["status"] == "completed"
    assert job["result"]["summary"]["queries"] == 40
    assert len(job["activities"]) >= 42
    assert client.get("/api/v1/evaluations/latest").json()["rag"]["job_id"] == job_id
    assert client.post("/api/v1/evaluations/extraction/run").status_code == 409
    assert client.get("/api/v1/evaluations/not-a-job").status_code == 404
