from __future__ import annotations

import copy
import threading
from datetime import datetime, timezone
from uuid import uuid4

from app.evaluation.extraction import run_extraction_evaluation
from app.evaluation.rag import run_rag_evaluation
from app.observability import trace_scope


class EvaluationAlreadyRunning(RuntimeError):
    pass


class EvaluationJobManager:
    def __init__(self) -> None:
        self._jobs: dict[str, dict] = {}
        self._latest: dict[str, str] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def start(self, kind: str) -> dict:
        runner = {"rag": run_rag_evaluation, "extraction": run_extraction_evaluation}.get(kind)
        if runner is None:
            raise ValueError("Unknown evaluation kind")
        with self._lock:
            if any(job["kind"] == kind and job["status"] in {"queued", "running"} for job in self._jobs.values()):
                raise EvaluationAlreadyRunning(f"A {kind} evaluation is already running")
            job_id = f"eval-{uuid4().hex[:12]}"
            self._jobs[job_id] = {
                "job_id": job_id,
                "kind": kind,
                "status": "queued",
                "created_at": self._now(),
                "started_at": None,
                "completed_at": None,
                "current": 0,
                "total": 0,
                "activities": [],
                "rows": [],
                "result": None,
                "error": None,
            }
        thread = threading.Thread(target=self._run, args=(job_id, runner), daemon=True)
        thread.start()
        return self.get(job_id)

    def _progress(self, job_id: str, event: dict) -> None:
        event = dict(event)
        row = event.pop("row", None)
        with self._lock:
            job = self._jobs[job_id]
            job["current"] = event.get("current", job["current"])
            job["total"] = event.get("total", job["total"])
            job["activities"].append({"timestamp": self._now(), **event})
            if row is not None:
                job["rows"].append(row)

    def _run(self, job_id: str, runner) -> None:
        with self._lock:
            kind = self._jobs[job_id]["kind"]
            self._jobs[job_id]["status"] = "running"
            self._jobs[job_id]["started_at"] = self._now()
        try:
            with trace_scope(f"evaluation:{kind}", source="evaluation"):
                result = runner(progress=lambda event: self._progress(job_id, event))
        except Exception as exc:
            with self._lock:
                job = self._jobs[job_id]
                job["status"] = "failed"
                job["error"] = f"{type(exc).__name__}: {exc}"
                job["completed_at"] = self._now()
            return
        with self._lock:
            job = self._jobs[job_id]
            job["result"] = result
            job["rows"] = result["rows"]
            job["status"] = "completed"
            job["completed_at"] = self._now()
            self._latest[job["kind"]] = job_id

    def get(self, job_id: str) -> dict:
        with self._lock:
            if job_id not in self._jobs:
                raise KeyError(job_id)
            return copy.deepcopy(self._jobs[job_id])

    def latest(self) -> dict:
        with self._lock:
            job_ids = dict(self._latest)
        return {
            kind: self.get(job_id) if job_id else None
            for kind in ("rag", "extraction")
            for job_id in (job_ids.get(kind),)
        }


evaluation_jobs = EvaluationJobManager()
