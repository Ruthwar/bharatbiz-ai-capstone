import argparse
import json
import os
import sys
from pathlib import Path

os.environ["LLM_PROVIDER"] = "none"

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.orchestration.workflow import process_message
from app.schemas.contracts import MessageSubmission


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a deterministic BharatBiz synthetic scenario")
    parser.add_argument("--scenario", required=True, choices=["SCN-003"])
    parser.add_argument("--mode", required=True, choices=["mock"])
    parser.add_argument("--data-dir", type=Path)
    args = parser.parse_args()

    fixture_path = PROJECT_ROOT / "data" / "synthetic" / "scenario_fixtures" / f"{args.scenario}.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    message = MessageSubmission.model_validate(fixture["message"])
    result = process_message(message, data_dir=args.data_dir)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    verification = result.get("verification")
    return 0 if verification and verification["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
