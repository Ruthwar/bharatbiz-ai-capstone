"""Run the frozen Track B gold set. Run: python scripts/eval_track_b.py [--json]."""

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

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.evaluation.track_b import ensure_frozen_inputs, run_track_b_evaluation  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="print the full machine-readable result")
    parser.add_argument("--case", action="append", dest="case_ids", help="run one case id (repeatable)")
    parser.add_argument("--split", choices=["dev", "confirm"], help="run one frozen split")
    parser.add_argument("--group", help="run one case group")
    parser.add_argument("--out", type=Path, help="write the full result to this JSON file")
    parser.add_argument("--verbose", action="store_true", help="print every failed case and check")
    args = parser.parse_args()

    integrity = ensure_frozen_inputs()
    if integrity:
        print("Track B integrity check failed:", "; ".join(integrity), file=sys.stderr)
        return 2

    result = run_track_b_evaluation(case_ids=args.case_ids, split=args.split, group=args.group)
    summary = result["summary"]

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    print(f"Track B gold evaluation · {result['version']} · deterministic mode")
    print(f"Dataset sha256: {result['dataset_sha256']}")
    print(
        f"Cases: {summary['cases']} · passed {summary['passed']} · failed {summary['failed']} "
        f"· pass rate {summary['pass_rate']:.1%}"
    )
    print()
    print(f"{'group':24} {'cases':>5} {'passed':>7} {'failed':>7} {'pass':>7}")
    for group, values in summary["by_group"].items():
        print(f"{group:24} {values['cases']:>5} {values['passed']:>7} {values['failed']:>7} {values['pass_rate']:>7.1%}")
    print()
    print(f"Latency p50 {summary['latency_ms_p50']:.1f} ms · p95 {summary['latency_ms_p95']:.1f} ms")
    print(f"Exceptions: {summary['exceptions']}")
    if summary["failure_labels"]:
        print("Failure labels:", ", ".join(f"{label}={count}" for label, count in summary["failure_labels"].items()))
    else:
        print("Failure labels: none")

    if args.verbose:
        print()
        for row in result["rows"]:
            if row["passed"]:
                continue
            print(f"{row['case_id']} [{row['group']}] {row['description']}")
            if row["exception"]:
                print(f"  exception: {row['exception']}")
            for check in row["checks"]:
                if not check["passed"]:
                    print(f"  {check['name']}: expected {check['expected']!r} actual {check['actual']!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
