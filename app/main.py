import os
from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.channels.chat import ChatInbound, to_submission
from app.extraction import configured_extractor
from app.orchestration.inbound import process_inbound
from app.orchestration.workflow import process_message
from app.schemas.contracts import MessageSubmission
from app.state import StateLoadError, StateVersionMismatch, load_business_state
from app.store.ledger import ledger

app = FastAPI(title="BharatBiz AI Capstone API", version="0.2.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "mode": "mock"}


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
    return process_inbound(to_submission(payload, state_version), ledger=ledger)


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
        "note": "Model output is validated; planning and decisions stay deterministic and human-approved.",
    }


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


@app.get("/api/v1/review/pending")
def pending_reviews() -> list[dict]:
    return ledger.pending_reviews()


class ReviewDecision(BaseModel):
    decision: Literal["approve", "reject"]
    reviewer: str = Field(min_length=1)


@app.post("/api/v1/review/{event_id}")
def decide(event_id: str, payload: ReviewDecision) -> dict:
    record = ledger.decide(event_id, payload.decision, payload.reviewer)
    if record is None:
        raise HTTPException(status_code=404, detail="Unknown review item")
    return record
