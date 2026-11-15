from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.agents.market import group_themes
from app.agents.orders import analyze_fulfilment
from app.agents.retailer import retailer_overview
from app.orchestration.review_actions import DraftSafetyError, decide_review
from app.schemas.retail import CasePriority, CaseStatus, SignalType
from app.state import StateLoadError, load_business_state
from app.store.ledger import ReviewDecisionError, ledger
from app.store.retail import RetailLifecycleError, retail_store

router = APIRouter(prefix="/api/v1/retail", tags=["retail"])


def _state():
    try:
        return load_business_state()
    except StateLoadError as exc:
        raise HTTPException(status_code=500, detail="Synthetic operational state is unavailable") from exc


@router.get("/fulfilment")
def fulfilment(sku_id: str | None = None, include_incoming: bool = False) -> dict:
    return analyze_fulfilment(_state(), sku_id, include_incoming).model_dump(mode="json")


@router.get("/retailers/{retailer_id}")
def retailer(retailer_id: str) -> dict:
    try:
        return retailer_overview(_state(), retailer_id, retail_store, datetime.now(timezone.utc))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/cases")
def cases(status: CaseStatus | None = None, retailer_id: str | None = None) -> list[dict]:
    return retail_store.list_cases(status=status, retailer_id=retailer_id)


@router.get("/cases/{case_id}")
def case(case_id: str) -> dict:
    record = retail_store.get_case(case_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Unknown case")
    record["activity"] = retail_store.case_activity(case_id)
    return record


class CaseUpdate(BaseModel):
    actor: str = Field(min_length=1)
    status: CaseStatus | None = None
    owner: str | None = Field(default=None, min_length=1)
    priority: CasePriority | None = None
    note: str | None = None
    resolution_note: str | None = None


@router.patch("/cases/{case_id}")
def update_case(case_id: str, payload: CaseUpdate) -> dict:
    try:
        return retail_store.update_case(case_id, **payload.model_dump())
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RetailLifecycleError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/drafts")
def drafts() -> list[dict]:
    return retail_store.list_drafts()


@router.get("/drafts/{draft_id}")
def draft(draft_id: str) -> dict:
    record = retail_store.get_draft(draft_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Unknown draft")
    return record


class DraftReview(BaseModel):
    event_id: str = Field(min_length=1)
    decision: Literal["approve", "reject"]
    reviewer: str = Field(min_length=1)
    note: str | None = None
    final_text: str | None = None


@router.post("/drafts/{draft_id}/review")
def review_draft(draft_id: str, payload: DraftReview) -> dict:
    try:
        record = decide_review(
            ledger,
            retail_store,
            payload.event_id,
            payload.decision,
            payload.reviewer,
            draft_id=draft_id,
            note=payload.note,
            final_text=payload.final_text,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ReviewDecisionError, RetailLifecycleError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except DraftSafetyError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if record is None:
        raise HTTPException(status_code=404, detail="Unknown review item")
    return {"review": record, "draft": retail_store.get_draft(draft_id)}


class ManualSend(BaseModel):
    sent_by: str = Field(min_length=1)


@router.post("/drafts/{draft_id}/mark-sent")
def mark_sent(draft_id: str, payload: ManualSend) -> dict:
    try:
        retail_store.mark_sent(draft_id, payload.sent_by)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RetailLifecycleError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return retail_store.get_draft(draft_id)


@router.get("/market-signals")
def market_signals(
    signal_type: SignalType | None = None,
    min_reporters: int = 1,
) -> list[dict]:
    if min_reporters < 1:
        raise HTTPException(status_code=422, detail="min_reporters must be at least 1")
    return [
        row.model_dump(mode="json")
        for row in group_themes(retail_store.observations(), signal_type, min_reporters)
    ]
