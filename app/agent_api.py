"""HTTP surface for the bounded agent runtime. Read-only: no approval, no execution."""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.agent_runtime.planner import AgentRequest, PlanValidationError, parse_plan
from app.agent_runtime.registry import build_registry, tool_catalog
from app.agent_runtime.runtime import agent_store, run_review
from app.state import StateLoadError, StateVersionMismatch, load_business_state

router = APIRouter()


class AgentReviewRequest(BaseModel):
    question: str = Field(min_length=3, max_length=2000)
    conversation_id: str | None = Field(default=None, max_length=64)
    intent: str | None = Field(default=None, max_length=64)
    sku_id: str | None = Field(default=None, max_length=64)
    supplier_id: str | None = Field(default=None, max_length=64)
    retailer_id: str | None = Field(default=None, max_length=64)
    delay_days: int | None = Field(default=None, ge=0, le=365)
    required_units: int | None = Field(default=None, ge=0)
    outflow_rupees: Decimal | None = Field(default=None, ge=0)
    state_version: str | None = Field(default=None, max_length=64)
    plan: dict | str | None = None


class PlanValidationRequest(BaseModel):
    plan: dict | str


@router.post("/api/v1/agent/review")
def agent_review(payload: AgentReviewRequest) -> dict:
    """Plan, execute and critique one read-only review with a recorded budget."""
    request = AgentRequest(
        question=payload.question,
        conversation_id=payload.conversation_id,
        intent=payload.intent,
        sku_id=payload.sku_id,
        supplier_id=payload.supplier_id,
        retailer_id=payload.retailer_id,
        delay_days=payload.delay_days,
        required_units=payload.required_units,
        outflow_rupees=str(payload.outflow_rupees) if payload.outflow_rupees is not None else None,
        state_version=payload.state_version,
        plan=payload.plan,
    )
    try:
        return run_review(request).to_dict()
    except StateVersionMismatch as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except StateLoadError as exc:
        raise HTTPException(status_code=500, detail="Synthetic operational state is unavailable") from exc


@router.post("/api/v1/agent/plan/validate")
def validate_plan(payload: PlanValidationRequest) -> dict:
    """Check a supplied plan without running it. Malformed input is reported, not raised."""
    try:
        state = load_business_state()
    except StateLoadError as exc:
        raise HTTPException(status_code=500, detail="Synthetic operational state is unavailable") from exc
    registry = build_registry(state)
    try:
        plan = parse_plan(payload.plan, registry)
    except PlanValidationError as exc:
        return {"valid": False, "error_code": exc.code, "message": exc.message}
    return {"valid": True, "error_code": None, "message": "", "plan": plan.to_dict()}


@router.get("/api/v1/agent/tools")
def agent_tools() -> dict:
    tools = tool_catalog()
    return {"count": len(tools), "read_only": True, "tools": tools}


@router.get("/api/v1/agent/sessions/{conversation_id}")
def agent_session(conversation_id: str) -> dict:
    turns = agent_store.turns(conversation_id)
    if not turns:
        raise HTTPException(status_code=404, detail="Unknown conversation")
    return {
        "conversation_id": conversation_id,
        "context": agent_store.context(conversation_id),
        "turns": turns,
    }
