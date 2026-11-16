import argparse
import json
import os
import sys
from pathlib import Path

os.environ["LLM_PROVIDER"] = "none"

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.scenarios.registry import get_scenario, list_scenarios
from app.scenarios.service import run_scenario


def expectation_value(key: str, result: dict):
    selected = result.get("selected_plan") or {}
    option = selected.get("supplier_option") or {}
    cash = selected.get("cash_projection") or {}
    scenario_view = result.get("scenario_view") or {}
    case = result.get("case_context") or {}
    market = result.get("market_context") or {}
    counterfactuals = result.get("counterfactuals") or []
    counter_selected = counterfactuals[0].get("selected_plan", {}) if counterfactuals else {}
    counter_option = counter_selected.get("supplier_option") or {}
    values = {
        "review_kind": result.get("review_kind"),
        "review_status": (result.get("recommendation") or {}).get("review_status"),
        "selected_candidate_id": selected.get("candidate_id"),
        "requested_units": selected.get("total_requested_units"),
        "fulfilled_units": selected.get("fulfilled_units"),
        "late_units": selected.get("late_units"),
        "unmet_units": selected.get("unmet_units"),
        "procurement_units": option.get("quantity_units"),
        "total_cost_rupees": selected.get("total_cost_rupees"),
        "scenario_arrival_date": option.get("scenario_arrival_date"),
        "ending_cash_rupees": cash.get("ending_cash_rupees"),
        "headroom_rupees": cash.get("headroom_rupees"),
        "verification_valid": (result.get("verification") or {}).get("valid"),
        "scenario_usable_units": scenario_view.get("scenario_usable_units"),
        "book_on_hand_units": scenario_view.get("book_on_hand_units"),
        "counted_on_hand_units": scenario_view.get("counted_on_hand_units"),
        "counterfactual": counterfactuals[0].get("name") if counterfactuals else None,
        "counterfactual_selected_candidate_id": counter_selected.get("candidate_id"),
        "counterfactual_procurement_units": counter_option.get("quantity_units"),
        "clarification_slot": case.get("clarification_slot"),
        "matched_order_count": case.get("matched_order_count"),
        "unique_observation_count": market.get("unique_observation_count"),
        "distinct_reporter_count": market.get("distinct_reporter_count"),
        "corroboration": market.get("corroboration"),
        "verification_status": market.get("verification_status"),
        "creates_allocation_plan": result.get("selected_plan") is not None,
        "planning_status": (result.get("negotiation") or {}).get("status"),
        "planners_agree": (result.get("negotiation") or {}).get("planners_agree"),
        "ortools_status": (result.get("negotiation") or {}).get("ortools_status"),
        "ortools_candidate_id": (result.get("negotiation") or {}).get("ortools_candidate_id"),
        "infeasibility_reasons": (result.get("negotiation") or {}).get("infeasibility_reasons"),
        "distinct_retailer_count": market.get("distinct_retailer_count"),
        "reported_request_count": market.get("reported_request_count"),
        "catalogue_match": market.get("catalogue_match"),
        "assortment_changed": market.get("assortment_changed"),
    }
    if key not in values:
        raise KeyError(f"No evaluator is registered for expectation {key}")
    return values[key]


def evaluate(scenario_id: str) -> dict:
    fixture = get_scenario(scenario_id)
    result = run_scenario(scenario_id)
    checks = []
    for key, expected in fixture.expected.items():
        actual = expectation_value(key, result)
        checks.append({"expectation": key, "expected": expected, "actual": actual, "passed": actual == expected})
    return {
        "scenario_id": scenario_id,
        "name": fixture.name,
        "passed": all(check["passed"] for check in checks),
        "check_count": len(checks),
        "checks": checks,
    }


def main() -> int:
    scenarios = list_scenarios()
    parser = argparse.ArgumentParser(description="Evaluate BharatBiz scenario outputs against fixture expectations")
    parser.add_argument("--scenario", choices=[fixture.scenario_id for fixture in scenarios])
    args = parser.parse_args()
    scenario_ids = [args.scenario] if args.scenario else [fixture.scenario_id for fixture in scenarios]
    results = [evaluate(scenario_id) for scenario_id in scenario_ids]
    passed = sum(result["passed"] for result in results)
    report = {"total": len(results), "passed": passed, "failed": len(results) - passed, "results": results}
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
