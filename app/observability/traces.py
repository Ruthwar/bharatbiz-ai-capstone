"""SQLite trace store for model and retrieval calls.

One row is one span. A span belongs to a trace: the work triggered by one message, one
scenario run or one evaluation job. The shape mirrors Langfuse (trace -> generation/span)
so the same records can be exported later, but nothing is sent anywhere unless an export
is explicitly configured. Recording is fail-safe: a tracing error never fails a request.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Iterator
from uuid import uuid4

logger = logging.getLogger(__name__)

TRACE_KINDS = ("generation", "retrieval", "fallback", "agent", "tool")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _int_or_none(value) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


@dataclass
class TraceScope:
    trace_id: str
    session: str
    scenario_id: str | None = None
    source: str = "direct"


_CURRENT: ContextVar[TraceScope | None] = ContextVar("bharatbiz_trace_scope", default=None)


class TraceStore:
    """Append-only span table. Reads aggregate in Python; the demo volume is small."""

    def __init__(self, path: str | Path = ":memory:") -> None:
        self._lock = Lock()
        self._path = str(path)
        self._conn = self._open()

    def _open(self) -> sqlite3.Connection:
        try:
            if self._path != ":memory:":
                Path(self._path).parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(self._path, check_same_thread=False)
        except (sqlite3.Error, OSError):
            logger.warning("trace database unavailable at %s; tracing stays in memory", self._path, exc_info=True)
            self._path = ":memory:"
            conn = sqlite3.connect(":memory:", check_same_thread=False)
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS llm_trace (
                span_id TEXT PRIMARY KEY,
                trace_id TEXT NOT NULL,
                session TEXT NOT NULL,
                scenario_id TEXT,
                source TEXT NOT NULL,
                step TEXT NOT NULL,
                kind TEXT NOT NULL,
                provider TEXT,
                model TEXT,
                prompt_version TEXT,
                started_at TEXT NOT NULL,
                latency_ms INTEGER,
                prompt_tokens INTEGER,
                completion_tokens INTEGER,
                status TEXT NOT NULL,
                error TEXT,
                detail TEXT NOT NULL,
                exported INTEGER NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS llm_trace_trace ON llm_trace (trace_id);
            CREATE INDEX IF NOT EXISTS llm_trace_started ON llm_trace (started_at);
            """
        )
        conn.commit()
        return conn

    @property
    def database(self) -> str:
        return self._path

    def record(self, span: dict) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR IGNORE INTO llm_trace (span_id, trace_id, session, scenario_id, source, step, "
                "kind, provider, model, prompt_version, started_at, latency_ms, prompt_tokens, "
                "completion_tokens, status, error, detail, exported) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)",
                (
                    span["span_id"],
                    span["trace_id"],
                    span["session"],
                    span["scenario_id"],
                    span["source"],
                    span["step"],
                    span["kind"],
                    span["provider"],
                    span["model"],
                    span["prompt_version"],
                    span["started_at"],
                    span["latency_ms"],
                    span["prompt_tokens"],
                    span["completion_tokens"],
                    span["status"],
                    span["error"],
                    json.dumps(span["detail"], ensure_ascii=False, default=str),
                ),
            )
            self._conn.commit()

    def mark_exported(self, span_id: str) -> None:
        with self._lock:
            self._conn.execute("UPDATE llm_trace SET exported = 1 WHERE span_id = ?", (span_id,))
            self._conn.commit()

    def spans(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT span_id, trace_id, session, scenario_id, source, step, kind, provider, model, "
                "prompt_version, started_at, latency_ms, prompt_tokens, completion_tokens, status, error, "
                "detail, exported FROM llm_trace ORDER BY rowid"
            ).fetchall()
        keys = (
            "span_id", "trace_id", "session", "scenario_id", "source", "step", "kind", "provider",
            "model", "prompt_version", "started_at", "latency_ms", "prompt_tokens",
            "completion_tokens", "status", "error", "detail", "exported",
        )
        spans = []
        for row in rows:
            span = dict(zip(keys, row))
            try:
                span["detail"] = json.loads(span["detail"])
            except (TypeError, json.JSONDecodeError):
                span["detail"] = {}
            span["exported"] = bool(span["exported"])
            spans.append(span)
        return spans

    def trace(self, trace_id: str) -> dict | None:
        spans = [span for span in self.spans() if span["trace_id"] == trace_id]
        if not spans:
            return None
        spans.sort(key=lambda span: span["started_at"])
        return {
            "trace_id": trace_id,
            "session": spans[0]["session"],
            "source": spans[0]["source"],
            "scenario_id": spans[0]["scenario_id"],
            "spans": spans,
        }

    def summary(self, recent_limit: int = 40, run_limit: int = 30) -> dict:
        spans = self.spans()
        generations = [span for span in spans if span["kind"] == "generation"]
        retrieval = [span for span in spans if span["kind"] == "retrieval"]
        fallbacks = [span for span in spans if span["kind"] == "fallback"]
        agent_spans = [span for span in spans if span["kind"] == "agent"]
        tool_calls = [span for span in spans if span["kind"] == "tool"]
        errors = [span for span in spans if span["status"] == "error"]
        tokens = sum((span["prompt_tokens"] or 0) + (span["completion_tokens"] or 0) for span in generations)
        latencies = sorted(span["latency_ms"] for span in generations if span["latency_ms"] is not None)

        def percentile(values: list[int], share: float) -> float | None:
            if not values:
                return None
            index = min(len(values) - 1, max(0, round(share * (len(values) - 1))))
            return float(values[index])

        rate = _cost_rate()
        return {
            "database": self.database,
            "totals": {
                "spans": len(spans),
                "generations": len(generations),
                "retrieval_calls": len(retrieval),
                "fallbacks": len(fallbacks),
                "agent_spans": len(agent_spans),
                "tool_calls": len(tool_calls),
                "errors": len(errors),
                "exported": sum(1 for span in spans if span["exported"]),
            },
            "tokens": {
                "prompt": sum(span["prompt_tokens"] or 0 for span in generations),
                "completion": sum(span["completion_tokens"] or 0 for span in generations),
                "total": tokens,
            },
            "latency_ms": {
                "average": round(sum(latencies) / len(latencies), 1) if latencies else None,
                "p50": percentile(latencies, 0.50),
                "p95": percentile(latencies, 0.95),
                "max": max(latencies) if latencies else None,
            },
            "cost": {
                "rate_per_1k_tokens": rate,
                "estimated": round(tokens / 1000 * rate, 6) if rate is not None else None,
                "basis": "configured illustrative rate" if rate is not None else "not priced",
            },
            "models": _group(
                generations,
                lambda span: {"provider": span["provider"] or "—", "model": span["model"] or "—"},
            ),
            "by_step": _group(spans, lambda span: {"step": span["step"], "kind": span["kind"]}),
            "sessions": _group(
                spans,
                lambda span: {"session": span["session"], "source": span["source"]},
                sort_key=lambda row: row["last_at"] or "",
                newest_first=True,
            ),
            "scenarios": _group(
                [span for span in spans if span["scenario_id"]],
                lambda span: {"scenario_id": span["scenario_id"]},
            ),
            "recent": [
                {
                    "span_id": span["span_id"],
                    "trace_id": span["trace_id"],
                    "session": span["session"],
                    "scenario_id": span["scenario_id"],
                    "step": span["step"],
                    "kind": span["kind"],
                    "model": span["model"],
                    "prompt_version": span["prompt_version"],
                    "started_at": span["started_at"],
                    "latency_ms": span["latency_ms"],
                    "prompt_tokens": span["prompt_tokens"],
                    "completion_tokens": span["completion_tokens"],
                    "status": span["status"],
                    "error": span["error"],
                    "exported": span["exported"],
                    "detail": span["detail"],
                }
                for span in list(reversed(spans))[:recent_limit]
            ],
            "runs": _runs(spans, run_limit),
        }

    def reset(self) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM llm_trace")
            self._conn.commit()


def _cost_rate() -> float | None:
    raw = os.getenv("BHARATBIZ_TRACE_COST_PER_1K_TOKENS", "").strip()
    if not raw:
        return None
    try:
        rate = float(raw)
    except ValueError:
        return None
    return rate if rate >= 0 else None


def _group(spans: list[dict], key, sort_key=None, newest_first: bool = False) -> list[dict]:
    groups: dict[tuple, dict] = {}
    for span in spans:
        labels = key(span)
        group_key = tuple(labels.values())
        row = groups.get(group_key)
        if row is None:
            row = {
                **labels,
                "spans": 0,
                "generations": 0,
                "errors": 0,
                "tokens": 0,
                "_latency": [],
                "first_at": span["started_at"],
                "last_at": span["started_at"],
            }
            groups[group_key] = row
        row["spans"] += 1
        if span["kind"] == "generation":
            row["generations"] += 1
            row["tokens"] += (span["prompt_tokens"] or 0) + (span["completion_tokens"] or 0)
            if span["latency_ms"] is not None:
                row["_latency"].append(span["latency_ms"])
        if span["status"] == "error":
            row["errors"] += 1
        row["first_at"] = min(row["first_at"], span["started_at"])
        row["last_at"] = max(row["last_at"], span["started_at"])
    result = []
    for row in groups.values():
        latencies = row.pop("_latency")
        row["avg_latency_ms"] = round(sum(latencies) / len(latencies), 1) if latencies else None
        result.append(row)
    result.sort(key=sort_key or (lambda row: row["spans"]), reverse=newest_first or sort_key is None)
    return result


def _runs(spans: list[dict], limit: int) -> list[dict]:
    grouped: dict[str, list[dict]] = {}
    for span in spans:
        grouped.setdefault(span["trace_id"], []).append(span)
    runs = []
    for trace_id, items in grouped.items():
        ordered = sorted(items, key=lambda span: span["started_at"])
        steps = []
        for span in ordered:
            if span["step"] not in steps:
                steps.append(span["step"])
        runs.append(
            {
                "trace_id": trace_id,
                "session": ordered[0]["session"],
                "source": ordered[0]["source"],
                "scenario_id": ordered[0]["scenario_id"],
                "started_at": ordered[0]["started_at"],
                "finished_at": ordered[-1]["started_at"],
                "spans": len(ordered),
                "generations": sum(1 for span in ordered if span["kind"] == "generation"),
                "retrieval_calls": sum(1 for span in ordered if span["kind"] == "retrieval"),
                "tokens": sum(
                    (span["prompt_tokens"] or 0) + (span["completion_tokens"] or 0)
                    for span in ordered
                    if span["kind"] == "generation"
                ),
                "errors": sum(1 for span in ordered if span["status"] == "error"),
                "status": "error" if any(span["status"] == "error" for span in ordered) else "ok",
                "steps": steps,
            }
        )
    runs.sort(key=lambda run: run["started_at"], reverse=True)
    return runs[:limit]


@contextmanager
def trace_scope(
    session: str,
    *,
    scenario_id: str | None = None,
    source: str = "direct",
) -> Iterator[TraceScope]:
    """Group spans from one unit of work. Nested scopes keep the outer trace."""
    active = _CURRENT.get()
    if active is not None:
        yield active
        return
    scope = TraceScope(
        trace_id=f"trace-{uuid4().hex[:12]}",
        session=session,
        scenario_id=scenario_id,
        source=source,
    )
    token = _CURRENT.set(scope)
    try:
        yield scope
    finally:
        _CURRENT.reset(token)


def current_trace() -> TraceScope | None:
    return _CURRENT.get()


def record_span(
    step: str,
    kind: str,
    *,
    provider: str | None = None,
    model: str | None = None,
    prompt_version: str | None = None,
    started_at: str | None = None,
    latency_ms: int | float | None = None,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    status: str = "ok",
    error: str | None = None,
    detail: dict | None = None,
) -> None:
    """Persist one span. Never raises: observability must not break the request."""
    try:
        scope = _CURRENT.get()
        span = {
            "span_id": f"span-{uuid4().hex[:16]}",
            "trace_id": scope.trace_id if scope else f"trace-{uuid4().hex[:12]}",
            "session": scope.session if scope else "standalone",
            "scenario_id": scope.scenario_id if scope else None,
            "source": scope.source if scope else "direct",
            "step": step,
            "kind": kind,
            "provider": provider,
            "model": model,
            "prompt_version": prompt_version,
            "started_at": started_at or _now(),
            "latency_ms": _int_or_none(latency_ms),
            "prompt_tokens": _int_or_none(prompt_tokens),
            "completion_tokens": _int_or_none(completion_tokens),
            "status": status,
            "error": str(error)[:300] if error else None,
            "detail": detail or {},
        }
        trace_store.record(span)
        from app.observability.export import export_span

        export_span(span)
    except Exception:
        logger.warning("trace recording failed for step=%s", step, exc_info=True)


def record_retrieval(
    query: str,
    documents: list[str],
    latency_ms: int | float,
    *,
    top_k: int | None = None,
    hits: int | None = None,
    error: str | None = None,
) -> None:
    """Record a retrieval only inside a trace; the Knowledge tab stays untraced."""
    if _CURRENT.get() is None:
        return
    record_span(
        "retrieval",
        "retrieval",
        latency_ms=latency_ms,
        status="error" if error else "ok",
        error=error,
        detail={
            "query": query[:300],
            "documents": documents[:12],
            "top_k": top_k,
            "hits": hits if hits is not None else len(documents),
        },
    )


def reset_traces() -> None:
    trace_store.reset()


def _default_path() -> str:
    configured = os.getenv("BHARATBIZ_TRACE_DB")
    if configured:
        return configured
    return str(Path(__file__).resolve().parents[2] / "data" / "runtime" / "traces.sqlite3")


trace_store = TraceStore(_default_path())
