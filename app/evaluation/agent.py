"""Measured agent-runtime evaluation over a frozen task set.

Each task runs the deterministic planner -> executor -> critic loop with an isolated session
store. No model call is made and no business state is written. A task counts as complete when
the critique passes and every policy document the intent depends on is cited in force.
"""

from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from app.agent_runtime.planner import AgentRequest
from app.agent_runtime.runtime import run_review
from app.agent_runtime.store import AgentSessionStore

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TASKS = PROJECT_ROOT / "data" / "eval" / "track_b" / "agent_tasks.jsonl"
VERSION = "track_b_agent_v1"


def _tasks() -> tuple[list[dict], str]:
    payload = TASKS.read_bytes()
    rows = [json.loads(line) for line in payload.decode("utf-8").splitlines() if line.strip()]
    if not rows:
        raise ValueError("Agent task set is empty")
    return rows, hashlib.sha256(payload).hexdigest()


def _request(task: dict) -> AgentRequest:
    return AgentRequest(
        question=task["question"],
        intent=task["intent"],
        sku_id=task.get("sku_id"),
        supplier_id=task.get("supplier_id"),
        retailer_id=task.get("retailer_id"),
        delay_days=task.get("delay_days"),
        required_units=task.get("required_units"),
        outflow_rupees=task.get("outflow_rupees"),
    )


def _percentile(values: list[float], share: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(len(ordered) * share) - 1))
    return round(ordered[index], 1)


def run_agent_evaluation(progress: Callable[[dict], None] | None = None) -> dict:
    tasks, tasks_sha = _tasks()
    total = len(tasks)
    rows: list[dict] = []
    labels: dict[str, int] = {}
    taxonomy: dict[str, int] = {}
    latencies: list[float] = []
    completed = 0

    if progress:
        progress(
            {
                "step": "dataset_loaded",
                "title": f"Loaded {total} frozen agent tasks",
                "current": 0,
                "total": total,
                "detail": "Deterministic planner; each task uses an isolated session store.",
            }
        )

    for index, task in enumerate(tasks, start=1):
        started = time.perf_counter()
        error = None
        try:
            run = run_review(_request(task), store=AgentSessionStore(":memory:")).to_dict()
        except Exception as exc:  # noqa: BLE001 - a crash is a recorded failure, not a stop
            error = f"{type(exc).__name__}: {exc}"
            run = {}
        duration_ms = round((time.perf_counter() - started) * 1000, 1)
        citations = [citation["document_id"] for citation in run.get("citations", [])]
        expected = list(task.get("expected_documents") or [])
        missing = [document_id for document_id in expected if document_id not in citations]
        passed = bool(run) and run["status"] == "ok" and not missing and error is None
        completed += int(passed)
        if run:
            latencies.append(float(run["usage"]["elapsed_ms"]))
            for label in run["failure_labels"]:
                labels[label] = labels.get(label, 0) + 1
            for label, category in run["failure_taxonomy"].items():
                taxonomy[category] = taxonomy.get(category, 0) + 1
        row = {
            "task_id": task["task_id"],
            "intent": task["intent"],
            "question": task["question"],
            "status": run.get("status", "error"),
            "completed": passed,
            "tool_calls": run.get("usage", {}).get("tool_calls", 0),
            "estimated_tokens": run.get("usage", {}).get("estimated_tokens", 0),
            "duration_ms": round(float(run.get("usage", {}).get("elapsed_ms", duration_ms)), 1),
            "retries": run.get("usage", {}).get("retries", 0),
            "citations": citations,
            "expected_documents": expected,
            "missing_documents": missing,
            "failure_labels": run.get("failure_labels", []),
            "taxonomy": run.get("failure_taxonomy", {}),
            "error": error,
        }
        rows.append(row)
        if progress:
            progress(
                {
                    "step": f"task_{task['task_id']}",
                    "title": f"{task['task_id']} · {task['intent'].replace('_', ' ')}",
                    "detail": f"{'complete' if passed else 'incomplete'} · {row['tool_calls']} tool calls · "
                    f"{len(citations)} citations",
                    "outcome": "pass" if passed else "fail",
                    "current": index,
                    "total": total,
                    "row": row,
                }
            )

    calls = [row["tool_calls"] for row in rows]
    tokens = [row["estimated_tokens"] for row in rows]
    summary = {
        "tasks": total,
        "completed": completed,
        "completion_rate": round(completed / total, 4) if total else 0.0,
        "avg_tool_calls": round(sum(calls) / len(calls), 2) if calls else 0.0,
        "avg_estimated_tokens": round(sum(tokens) / len(tokens), 1) if tokens else 0.0,
        "latency_ms_p50": _percentile(latencies, 0.50),
        "latency_ms_p95": _percentile(latencies, 0.95),
        "failure_labels": dict(sorted(labels.items())),
        "taxonomy": dict(sorted(taxonomy.items())),
        "exceptions": sum(1 for row in rows if row["error"]),
        "by_intent": {
            intent: {
                "tasks": sum(1 for row in rows if row["intent"] == intent),
                "completed": sum(1 for row in rows if row["intent"] == intent and row["completed"]),
            }
            for intent in dict.fromkeys(row["intent"] for row in rows)
        },
    }
    return {
        "version": VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tasks": total,
        "tasks_sha256": tasks_sha,
        "summary": summary,
        "rows": rows,
    }
