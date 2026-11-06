from fastapi import FastAPI, HTTPException

from app.orchestration.workflow import process_message
from app.schemas.contracts import MessageSubmission
from app.state import StateLoadError, StateVersionMismatch

app = FastAPI(title="BharatBiz AI Capstone API", version="0.1.0")


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
