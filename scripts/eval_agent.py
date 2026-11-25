"""Run the frozen agent task set. Run: python scripts/eval_agent.py [--json]."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("LLM_PROVIDER", "none")
os.environ.setdefault("BHARATBIZ_LEDGER_DB", ":memory:")
os.environ.setdefault("BHARATBIZ_RETAIL_DB", ":memory:")
os.environ.setdefault("BHARATBIZ_RAG_DB", ":memory:")
os.environ.setdefault("BHARATBIZ_TRACE_DB", ":memory:")
os.environ.setdefault("BHARATBIZ_TRACE_EXPORT", "none")
os.environ.setdefault("BHARATBIZ_AGENT_DB", ":memory:")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.evaluation.agent import run_agent_evaluation  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="print the full machine-readable result")
    parser.add_argument("--out", type=Path, help="write the full result to this JSON file")
    args = parser.parse_args()

    result = run_agent_evaluation()
    summary = result["summary"]

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    print(f"Agent evaluation · {result['version']} · deterministic planner, no model call")
    print(f"Task set sha256: {result['tasks_sha256']}")
    print(
        f"Tasks: {summary['tasks']} · completed {summary['completed']} "
        f"· completion {summary['completion_rate']:.1%} · avg tool calls {summary['avg_tool_calls']:.2f}"
    )
    print(
        f"Tokens/task {summary['avg_estimated_tokens']:.0f} (characters/4 estimate) "
        f"· latency p50 {summary['latency_ms_p50']:.1f} ms · p95 {summary['latency_ms_p95']:.1f} ms"
    )
    print(f"Exceptions: {summary['exceptions']}")
    print(
        "Failure labels:",
        ", ".join(f"{label}={count}" for label, count in summary["failure_labels"].items()) or "none",
    )
    print()
    print(f"{'task':9} {'intent':22} {'done':>5} {'calls':>6} {'tokens':>7} {'ms':>7}")
    for row in result["rows"]:
        print(
            f"{row['task_id']:9} {row['intent']:22} {'yes' if row['completed'] else 'no':>5} "
            f"{row['tool_calls']:>6} {row['estimated_tokens']:>7} {row['duration_ms']:>7.1f}"
        )
    return 0 if summary["completed"] == summary["tasks"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
