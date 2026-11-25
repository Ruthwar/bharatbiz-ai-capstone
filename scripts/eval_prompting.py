"""Compare prompting strategies on the held-out extraction set.

Run: python scripts/eval_prompting.py [--json] [--out data/evaluation_runs/prompting.json]
Requires a configured model for anything beyond the rules baseline (see .env.example).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("BHARATBIZ_TRACE_EXPORT", "none")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.evaluation.prompting import STRATEGIES, run_prompting_evaluation, summarize  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="print the full machine-readable result")
    parser.add_argument("--out", type=Path, help="write the full result to this JSON file")
    parser.add_argument("--limit", type=int, help="run only the first N held-out examples")
    parser.add_argument(
        "--strategies",
        help="comma-separated subset of: " + ", ".join(spec.name for spec in STRATEGIES),
    )
    parser.add_argument("--verbose", action="store_true", help="print each example as it completes")
    args = parser.parse_args()

    chosen = STRATEGIES
    if args.strategies:
        wanted = {name.strip() for name in args.strategies.split(",") if name.strip()}
        unknown = wanted - {spec.name for spec in STRATEGIES}
        if unknown:
            print(f"Unknown strategies: {', '.join(sorted(unknown))}", file=sys.stderr)
            return 2
        chosen = tuple(spec for spec in STRATEGIES if spec.name in wanted)

    records = None
    if args.limit:
        from app.evaluation.extraction import load_held_out_records

        records = load_held_out_records()[: args.limit]

    def progress(event: dict) -> None:
        if not args.verbose:
            return
        row = event["row"]
        parts = [f"{event['position']:>2}/{event['total']}", row["message_id"]]
        for name, values in row["results"].items():
            parts.append(f"{name}: {'exact' if values['record_exact'] else 'miss'}")
        print(" · ".join(parts))

    result = run_prompting_evaluation(records=records, strategies=chosen, progress=progress)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(summarize(result))
        if args.out:
            print(f"\nSaved: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
