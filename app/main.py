from fastapi import FastAPI

from app.schemas.contracts import MessageSubmission
from app.orchestration.workflow import process_message

app = FastAPI(title="BharatBiz AI Capstone API", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "mode": "mock"}


@app.post("/api/v1/messages/process")
def submit_message(message: MessageSubmission) -> dict:
    """Process a message in deterministic mock mode and retain evidence/uncertainty."""
    return process_message(message)
