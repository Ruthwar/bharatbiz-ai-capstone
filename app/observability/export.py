"""Optional export of local spans to a Langfuse instance.

Off by default. Enabled only when BHARATBIZ_TRACE_EXPORT=langfuse and the three Langfuse
settings are present. The batch uses the documented ingestion endpoint; this has not been
verified against a live Langfuse deployment in this project, so treat it as a hook, not a
tested integration. Export failures never affect the request that produced the span.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from threading import Thread
from uuid import uuid4

import httpx

from app.observability.traces import trace_store

logger = logging.getLogger(__name__)


def export_settings() -> dict:
    host = os.getenv("LANGFUSE_HOST", "").strip().rstrip("/")
    public_key = os.getenv("LANGFUSE_PUBLIC_KEY", "").strip()
    secret_key = os.getenv("LANGFUSE_SECRET_KEY", "").strip()
    requested = os.getenv("BHARATBIZ_TRACE_EXPORT", "").strip().lower() == "langfuse"
    if not requested:
        return {"enabled": False, "host": "", "reason": "Local trace store only (default)."}
    missing = [
        name
        for name, value in (
            ("LANGFUSE_HOST", host),
            ("LANGFUSE_PUBLIC_KEY", public_key),
            ("LANGFUSE_SECRET_KEY", secret_key),
        )
        if not value
    ]
    if missing:
        return {"enabled": False, "host": host, "reason": "Missing " + ", ".join(missing) + "."}
    return {"enabled": True, "host": host, "reason": "Spans are also sent to the configured Langfuse instance."}


def _end_time(span: dict) -> str:
    try:
        start = datetime.fromisoformat(span["started_at"])
    except (TypeError, ValueError):
        return datetime.now(timezone.utc).isoformat()
    return (start + timedelta(milliseconds=span.get("latency_ms") or 0)).isoformat()


def _batch(span: dict) -> tuple[dict, dict]:
    now = datetime.now(timezone.utc).isoformat()
    trace_event = {
        "id": str(uuid4()),
        "type": "trace-create",
        "timestamp": now,
        "body": {
            "id": span["trace_id"],
            "name": span.get("scenario_id") or span["session"],
            "sessionId": span["session"],
            "timestamp": span["started_at"],
            "metadata": {"source": span["source"], "scenario_id": span.get("scenario_id")},
        },
    }
    metadata = {
        "provider": span.get("provider"),
        "prompt_version": span.get("prompt_version"),
        "status": span["status"],
        "detail": span.get("detail") or {},
    }
    if span["kind"] == "generation":
        body = {
            "id": span["span_id"],
            "traceId": span["trace_id"],
            "name": span["step"],
            "model": span.get("model") or "not reported",
            "startTime": span["started_at"],
            "endTime": _end_time(span),
            "level": "ERROR" if span["status"] == "error" else "DEFAULT",
            "metadata": metadata,
        }
        if span.get("error"):
            body["statusMessage"] = span["error"]
        if span.get("prompt_tokens") is not None or span.get("completion_tokens") is not None:
            body["usage"] = {
                "input": span.get("prompt_tokens"),
                "output": span.get("completion_tokens"),
            }
        event_type = "generation-create"
    else:
        detail = span.get("detail") or {}
        body = {
            "id": span["span_id"],
            "traceId": span["trace_id"],
            "name": span["step"],
            "startTime": span["started_at"],
            "endTime": _end_time(span),
            "level": "ERROR" if span["status"] == "error" else "DEFAULT",
            "input": detail.get("query"),
            "output": ", ".join(detail.get("documents") or []) or None,
            "metadata": metadata,
        }
        if span.get("error"):
            body["statusMessage"] = span["error"]
        event_type = "span-create"
    return {
        "id": str(uuid4()),
        "type": event_type,
        "timestamp": now,
        "body": body,
    }, trace_event


def _post_batch(events: list[dict]) -> None:
    host = os.getenv("LANGFUSE_HOST", "").strip().rstrip("/")
    public_key = os.getenv("LANGFUSE_PUBLIC_KEY", "").strip()
    secret_key = os.getenv("LANGFUSE_SECRET_KEY", "").strip()
    timeout = float(os.getenv("LANGFUSE_TIMEOUT_SECONDS", "5"))
    with httpx.Client(timeout=timeout, verify=os.getenv("LANGFUSE_CA_BUNDLE") or True, trust_env=False) as client:
        response = client.post(
            f"{host}/api/public/ingestion",
            auth=(public_key, secret_key),
            json={"batch": events},
        )
        response.raise_for_status()


def _deliver(span: dict) -> None:
    try:
        event, trace_event = _batch(span)
        _post_batch([trace_event, event])
        trace_store.mark_exported(span["span_id"])
    except Exception as exc:
        logger.warning("langfuse export failed span=%s type=%s", span["span_id"], type(exc).__name__)


def export_span(span: dict, *, background: bool = True) -> bool:
    """Queue one span for export. Returns True when a delivery was queued."""
    if not export_settings()["enabled"] or span.get("exported"):
        return False
    if background:
        Thread(target=_deliver, args=(span,), daemon=True).start()
    else:
        _deliver(span)
    return True
