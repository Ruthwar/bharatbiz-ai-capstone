import argparse
import json
import os
import sys
from pathlib import Path

os.environ["LLM_PROVIDER"] = "none"

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.scenarios.registry import list_scenarios
from app.scenarios.service import run_scenario


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a deterministic BharatBiz synthetic scenario")
    parser.add_argument("--scenario", required=True, choices=[row.scenario_id for row in list_scenarios()])
    parser.add_argument("--mode", required=True, choices=["mock"])
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--persist-review", action="store_true")
    args = parser.parse_args()

    result = run_scenario(args.scenario, data_dir=args.data_dir, persist=args.persist_review)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    verification = result.get("verification")
    if verification is not None:
        return 0 if verification["valid"] else 1
    status = (result.get("recommendation") or {}).get("review_status")
    return 0 if status in {"pending_review", "needs_clarification"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
