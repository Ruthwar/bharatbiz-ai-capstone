import json
import subprocess
import sys
from pathlib import Path

import pytest

from app.evaluation.track_b import (
    DEFAULT_CASES_PATH,
    DEFAULT_MANIFEST_PATH,
    ensure_frozen_inputs,
    grade_expect,
    run_track_b_evaluation,
)
from app.evaluation.track_b_schema import (
    CASE_COUNT,
    CONFIRM_COUNT,
    DEV_COUNT,
    GROUPS,
    case_hash,
    file_hash,
    load_cases,
    validate_dataset,
)
from app.store.ledger import ledger as global_ledger

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def baseline():
    return run_track_b_evaluation()


def test_frozen_manifest_matches_dataset_and_protected_assets():
    cases = load_cases(DEFAULT_CASES_PATH)
    assert validate_dataset(cases) == []
    assert len(cases) == CASE_COUNT
    manifest = json.loads(DEFAULT_MANIFEST_PATH.read_text(encoding="utf-8"))
    assert manifest["version"] == "track_b_gold_v1.1"
    assert manifest["case_count"] == CASE_COUNT
    assert manifest["dataset_sha256"] == file_hash(DEFAULT_CASES_PATH)
    for case in cases:
        assert manifest["case_hashes"][case["case_id"]] == case_hash(case)

    protected = manifest["protected_assets"]
    for scenario_id, expected in protected["fixture_hashes"].items():
        assert file_hash(PROJECT_ROOT / "data/synthetic/scenario_fixtures" / f"{scenario_id}.json") == expected
    assert file_hash(PROJECT_ROOT / "data/eval/golden_queries.json") == protected["golden_queries_sha256"]
    assert file_hash(PROJECT_ROOT / "data/eval/heldout_extraction.jsonl") == protected["heldout_extraction_sha256"]
    assert file_hash(PROJECT_ROOT / "data/knowledge_docs/manifest.json") == protected["knowledge_manifest_sha256"]


def test_audit_copy_of_original_frozen_set_is_retained():
    v1_cases = PROJECT_ROOT / "data/eval/track_b/cases_v1.jsonl"
    v1_manifest = PROJECT_ROOT / "data/eval/track_b/manifest_v1.json"
    assert v1_cases.exists() and v1_manifest.exists()
    assert json.loads(v1_manifest.read_text(encoding="utf-8"))["version"] == "track_b_gold_v1"
    assert file_hash(v1_cases) != file_hash(DEFAULT_CASES_PATH)


def test_groups_and_splits_are_frozen():
    cases = load_cases(DEFAULT_CASES_PATH)
    assert sum(1 for case in cases if case["split"] == "dev") == DEV_COUNT
    assert sum(1 for case in cases if case["split"] == "confirm") == CONFIRM_COUNT
    counts = {group: sum(1 for case in cases if case["group"] == group) for group in GROUPS}
    assert counts == {
        "canonical_scenario": 15,
        "restatement": 15,
        "inbound_persistence": 15,
        "multi_turn": 10,
        "authority_security": 10,
        "intent_variant": 10,
        "edge_case": 5,
    }
    assert all(case["expect"]["no_autonomous_action"] is True for case in cases)


def test_integrity_check_and_builder_cli():
    assert ensure_frozen_inputs() == []
    completed = subprocess.run(
        [sys.executable, "scripts/build_track_b_goldset.py", "--check"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert "80 cases" in completed.stdout


def test_canonical_cases_pass_the_measured_baseline():
    result = run_track_b_evaluation(group="canonical_scenario")
    assert result["summary"]["cases"] == 15
    assert result["summary"]["passed"] == 15
    assert result["summary"]["failed"] == 0


def test_baseline_is_measured_and_never_autonomous(baseline):
    summary = baseline["summary"]
    assert summary["cases"] == CASE_COUNT
    assert summary["passed"] + summary["failed"] == CASE_COUNT
    assert summary["exceptions"] <= 1
    assert all(row["checks"] for row in baseline["rows"])
    assert all(row["failure_labels"] for row in baseline["rows"] if not row["passed"])
    assert "autonomy_violation" not in summary["failure_labels"]
    multi_turn = [row for row in baseline["rows"] if row["group"] == "multi_turn"]
    assert multi_turn
    assert all(any(check["name"].startswith("turn_1.") for check in row["checks"]) for row in multi_turn)


def test_evaluation_uses_isolated_stores():
    before = len(global_ledger.pending_reviews())
    result = run_track_b_evaluation(case_ids=["TB-031", "TB-061", "TB-062", "TB-080"])
    assert result["summary"]["cases"] == 4
    assert len(global_ledger.pending_reviews()) == before


def test_grader_detects_routing_selection_and_status_errors():
    payload = {
        "routed_action": "human_triage",
        "question": None,
        "result": {
            "event": {
                "intents": [{"intent": "baseline"}],
                "event_type": "baseline",
                "status": "pending_review",
                "uncertainties": [],
            },
            "review_kind": "operational_plan",
            "selected_plan": {"candidate_id": "stock-only"},
            "recommendation": {
                "review_status": "pending_review",
                "human_approval_required": True,
                "summary": "ok",
            },
            "verification": {"valid": True},
        },
    }
    checks = grade_expect(
        {
            "routed_action": "baseline_planning",
            "selected_candidate_id": "supplier-SUP-001",
            "review_status": "needs_clarification",
            "queue_delta": 1,
            "no_autonomous_action": True,
        },
        payload,
    )
    failed = {check["name"] for check in checks if not check["passed"]}
    assert failed == {"routed_action", "selected_candidate_id", "review_status", "queue_delta"}


def test_grader_flags_approved_or_executed_output():
    payload = {
        "routed_action": "baseline_planning",
        "result": {
            "event": {"intents": [{"intent": "baseline"}], "event_type": "baseline", "status": "pending_review"},
            "review_kind": "operational_plan",
            "selected_plan": {"candidate_id": "stock-only"},
            "recommendation": {
                "review_status": "approved",
                "human_approval_required": True,
                "summary": "ok",
            },
            "executed": True,
        },
    }
    checks = grade_expect({"no_autonomous_action": True}, payload)
    safety = next(check for check in checks if check["name"] == "no_autonomous_action")
    assert safety["passed"] is False
    assert any("approved" in violation for violation in safety["actual"])
    assert any("executed" in violation for violation in safety["actual"])
