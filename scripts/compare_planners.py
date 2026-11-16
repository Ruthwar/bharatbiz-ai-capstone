"""Compare deterministic ranking and OR-Tools on the same operational fixtures."""

import json
import os
import sys
from pathlib import Path

os.environ["LLM_PROVIDER"] = "none"

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.scenarios.registry import list_scenarios
from app.scenarios.service import run_scenario

OPERATIONAL = {"SCN-001", "SCN-002", "SCN-003", "SCN-004", "SCN-005", "SCN-008", "SCN-010"}


def compare(scenario_id: str) -> dict:
    result = run_scenario(scenario_id)
    negotiation = result.get("negotiation") or {}
    selected = (result.get("selected_plan") or {}).get("candidate_id")
    deterministic = negotiation.get("deterministic_candidate_id")
    ortools = negotiation.get("ortools_candidate_id")
    feasible = negotiation.get("status") == "feasible"
    problems = []
    if negotiation.get("planners_agree") is not True:
        problems.append("planners disagree")
    if deterministic != ortools:
        problems.append("candidate ids differ")
    if feasible and selected != deterministic:
        problems.append("published plan is not the deterministic selection")
    if not feasible and selected is not None:
        problems.append("infeasible run still published a plan")
    if not feasible and result["recommendation"]["review_status"] == "pending_review":
        problems.append("infeasible run was sent for approval")
    return {
        "scenario_id": scenario_id,
        "status": negotiation.get("status"),
        "deterministic_candidate_id": deterministic,
        "ortools_candidate_id": ortools,
        "ortools_status": negotiation.get("ortools_status"),
        "selected_candidate_id": selected,
        "passed": not problems,
        "problems": problems,
    }


def main() -> int:
    rows = [compare(fixture.scenario_id) for fixture in list_scenarios() if fixture.scenario_id in OPERATIONAL]
    passed = sum(row["passed"] for row in rows)
    report = {"total": len(rows), "passed": passed, "failed": len(rows) - passed, "results": rows}
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
