"""Measure retrieval ablations on the additive Track B corpus.

Run: python scripts/eval_rag_experiments.py [--json] [--out data/evaluation_runs/rag_experiments.json]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("LLM_PROVIDER", "none")
os.environ.setdefault("BHARATBIZ_TRACE_EXPORT", "none")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.evaluation.rag_experiments import run_rag_experiments, summarize  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="print the full machine-readable result")
    parser.add_argument("--out", type=Path, help="write the full result to this JSON file")
    args = parser.parse_args()

    result = run_rag_experiments()
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(summarize(result))
        if args.out:
            print(f"\nSaved: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
