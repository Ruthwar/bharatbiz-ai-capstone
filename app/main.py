import os
from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.agent_api import router as agent_router
from app.channels.chat import ChatInbound, to_submission
from app.decision import decision_model_status
from app.evaluation import EvaluationAlreadyRunning, evaluation_jobs
from app.extraction import configured_extractor
from app.observability.export import export_settings
from app.observability.traces import reset_traces, trace_store
from app.agent_runtime.runtime import agent_store
from app.orchestration.inbound import process_inbound
from app.orchestration.review_actions import DraftSafetyError, decide_review
from app.orchestration.workflow import process_message
from app.rag.corpus import DEFAULT_CORPUS_DIR, load_documents
from app.retail_api import router as retail_router
from app.safety import pii, response_cache, rate_limiter
from app.safety.injection import scan as scan_injection
from app.safety.middleware import RateLimitMiddleware, ReadCacheMiddleware
from app.scenarios.service import run_scenario, scenario_summaries
from app.schemas.contracts import MessageSubmission
from app.state import StateLoadError, StateVersionMismatch, load_business_state
from app.store.ledger import ReviewDecisionError, ledger
from app.store.retail import retail_store

app = FastAPI(title="BharatBiz AI Capstone API", version="0.2.0")
app.add_middleware(ReadCacheMiddleware)
app.add_middleware(RateLimitMiddleware)
app.include_router(retail_router)
app.include_router(agent_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "mode": "mock"}


@app.post("/api/v1/demo/reset")
def reset_demo() -> dict:
    ledger.reset()
    retail_store.reset()
    reset_traces()
    agent_store.reset()
    response_cache.reset()
    rate_limiter.reset()
    return {
        "status": "reset",
        "cleared": [
            "scenario_results",
            "pending_intakes",
            "review_queue",
            "retailer_interactions",
            "cases",
            "reply_drafts",
            "market_observations",
            "llm_traces",
            "agent_sessions",
        ],
    }


@app.get("/api/v1/observability")
def observability() -> dict:
    """Local model and retrieval spans, with the optional export configuration."""
    return {**trace_store.summary(), "export": export_settings()}


@app.get("/api/v1/safety/controls")
def safety_controls() -> dict:
    """Active production controls. No identifiers or configuration secrets are returned."""
    return {
        "cache": response_cache.stats(),
        "rate_limit": rate_limiter.snapshot(),
        "pii": {
            "redaction": "mask" if pii.redaction_enabled() else "off",
            "identifiers": list(pii.PII_TYPES),
            "note": "Applied to text sent to an external model; traces store counts, never values.",
        },
        "injection": {
            "mode": "detect_and_flag",
            "note": "Embedded instructions are recorded as advisory signals and never change routing, approval or plans.",
        },
        "containers": {
            "base_image": "python:3.12.10-slim",
            "runs_as": "non-root app user",
            "secrets_baked_in": False,
            "note": "Images run the API and dashboard separately; they were defined and statically checked here, not built.",
        },
        "human_approval_required": True,
        "autonomous_actions": False,
    }


class SafetyPreviewRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


@app.post("/api/v1/safety/preview")
def safety_preview(payload: SafetyPreviewRequest) -> dict:
    """Show masking and injection signals without calling a model or changing state."""
    masked, meta = pii.prepare_for_model(payload.text)
    signals = scan_injection(payload.text).summary()
    return {
        "original_length": len(payload.text),
        "masked": masked,
        "pii": meta,
        "injection": signals,
        "advisory_only": True,
        "note": "Masked preview only. No model call, routing change or approval is performed.",
    }


@app.get("/api/v1/safety/corpus-audit")
def corpus_audit() -> dict:
    """Scan the approved corpus for embedded instructions. Read-only and advisory."""
    documents = load_documents(DEFAULT_CORPUS_DIR)
    sections = 0
    flagged: list[dict] = []
    kinds: dict[str, int] = {}
    for document in documents:
        for section in document.sections:
            sections += 1
            scan = scan_injection(section.text)
            if not scan.flagged:
                continue
            for kind in scan.summary()["kinds"]:
                kinds[kind] = kinds.get(kind, 0) + 1
            flagged.append(
                {
                    "document_id": document.document_id,
                    "section_id": section.section_id,
                    "heading": section.heading,
                    "kinds": scan.summary()["kinds"],
                }
            )
    return {
        "documents": len(documents),
        "sections": sections,
        "flagged_documents": len({row["document_id"] for row in flagged}),
        "flagged_sections": len(flagged),
        "signals": dict(sorted(kinds.items())),
        "examples": flagged[:5],
        "mode": "detect_and_flag",
        "note": (
            "Retrieved passages are data, never instructions. A flagged document is reported to the "
            "operator and still cannot approve, execute or bypass human review."
        ),
    }


@app.get("/api/v1/observability/traces/{trace_id}")
def observability_trace(trace_id: str) -> dict:
    trace = trace_store.trace(trace_id)
    if trace is None:
        raise HTTPException(status_code=404, detail="Unknown trace")
    return trace


@app.post("/api/v1/messages/process")
def submit_message(message: MessageSubmission) -> dict:
    try:
        return process_message(message)
    except StateVersionMismatch as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except StateLoadError as exc:
        raise HTTPException(status_code=500, detail="Synthetic operational state is unavailable") from exc


@app.post("/api/v1/inbound")
def receive_inbound(payload: ChatInbound) -> dict:
    """Channel intake. Receipt is always acknowledged; processing failures route to triage."""
    try:
        state_version = payload.state_version or load_business_state().state_version
    except StateLoadError as exc:
        raise HTTPException(status_code=500, detail="Synthetic operational state is unavailable") from exc
    return process_inbound(
        to_submission(payload, state_version), ledger=ledger, decision_mode=payload.decision_mode
    )


@app.get("/api/v1/status")
def inference_status() -> dict:
    """Configuration of the extraction stage, without exposing credentials."""
    extractor = configured_extractor()
    enabled = extractor.name == "llm"
    return {
        "extractor": extractor.name,
        "llm_enabled": enabled,
        "provider": os.getenv("LLM_PROVIDER", "none") if enabled else "none",
        "model": getattr(extractor, "model", "") if enabled else "",
        "decision_llm_enabled": decision_model_status()["enabled"],
        "decision_model": decision_model_status()["model"],
        "note": "Extraction and recommendation modes are selectable; calculations, eligibility and human approval remain controlled.",
    }


@app.post("/api/v1/evaluations/{kind}/run", status_code=202)
def start_evaluation(kind: Literal["rag", "extraction", "track_b", "rag_experiments", "prompting", "agent"]) -> dict:
    if kind in {"extraction", "prompting"} and configured_extractor().name != "llm":
        raise HTTPException(
            status_code=409,
            detail="Enable LLM extraction to compare rules with the configured model.",
        )
    try:
        return evaluation_jobs.start(kind)
    except EvaluationAlreadyRunning as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/api/v1/evaluations/latest")
def latest_evaluations() -> dict:
    return evaluation_jobs.latest()


@app.get("/api/v1/evaluations/{job_id}")
def evaluation_status(job_id: str) -> dict:
    try:
        return evaluation_jobs.get(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Unknown evaluation job") from exc


@app.get("/api/v1/parties")
def party_directory() -> list[dict]:
    """Trade names for pickers in the demo UI; internal IDs remain the routing key."""
    try:
        state = load_business_state()
    except StateLoadError as exc:
        raise HTTPException(status_code=500, detail="Synthetic operational state is unavailable") from exc
    return [
        {"party_type": "supplier", "party_id": row["supplier_id"], "party_name": row["supplier_name"]}
        for row in state.suppliers
    ] + [
        {"party_type": "retailer", "party_id": row["retailer_id"], "party_name": row["retailer_name"]}
        for row in state.retailers
    ]


@app.get("/api/v1/scenarios")
def scenarios() -> list[dict]:
    return scenario_summaries()


class ScenarioRunRequest(BaseModel):
    persist_review: bool = False
    decision_mode: Literal["deterministic", "policy_grounded_llm"] = "deterministic"


@app.post("/api/v1/scenarios/{scenario_id}/run")
def execute_scenario(scenario_id: str, payload: ScenarioRunRequest | None = None) -> dict:
    if scenario_id not in {row["scenario_id"] for row in scenario_summaries()}:
        raise HTTPException(status_code=404, detail="Unknown scenario")
    try:
        return run_scenario(
            scenario_id,
            persist=bool(payload and payload.persist_review),
            decision_mode=payload.decision_mode if payload else "deterministic",
        )
    except (ValueError, StateVersionMismatch) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except StateLoadError as exc:
        raise HTTPException(status_code=500, detail="Synthetic operational state is unavailable") from exc


@app.get("/api/v1/review/pending")
def pending_reviews() -> list[dict]:
    return ledger.pending_reviews()


class ReviewDecision(BaseModel):
    decision: Literal["approve", "reject"]
    reviewer: str = Field(min_length=1)


@app.post("/api/v1/review/{event_id}")
def decide(event_id: str, payload: ReviewDecision) -> dict:
    try:
        record = decide_review(ledger, retail_store, event_id, payload.decision, payload.reviewer)
    except (ReviewDecisionError, DraftSafetyError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if record is None:
        raise HTTPException(status_code=404, detail="Unknown review item")
    return record
