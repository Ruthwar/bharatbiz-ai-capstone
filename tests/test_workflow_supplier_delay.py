import json
import subprocess
import sys
from pathlib import Path

from app.orchestration.workflow import process_message

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_complete_supplier_delay_workflow(demo_message):
    result = process_message(demo_message)

    assert result["mode"] == "rules_mock"
    assert result["event"]["status"] == "pending_review"
    facts = {fact["field"]: fact for fact in result["event"]["extracted_facts"]}
    assert facts["supplier_id"]["value"] == "SUP-005"
    assert facts["delay_days"]["value"] == "2"
    for fact in facts.values():
        start, end = fact["span_start"], fact["span_end"]
        assert demo_message.text[start:end] == fact["evidence_span"]
    assert result["event"]["inferences"]["catalogue_sku_id"] == "SKU-003"
    assert result["selected_plan"]["candidate_id"] == "supplier-SUP-002"
    assert result["verification"] == {"valid": True, "violations": []}
    assert result["recommendation"]["review_status"] == "pending_review"


def test_workflow_is_deterministic(demo_message):
    assert process_message(demo_message) == process_message(demo_message)


def test_ambiguous_product_requires_clarification(demo_message):
    ambiguous = demo_message.model_copy(
        update={
            "message_id": "DEMO-SCN-003-AMBIGUOUS",
            "text": "Supplier SUP-005 reports a two-day delay for Rice; revised date is not confirmed.",
        }
    )

    result = process_message(ambiguous)

    assert result["event"]["status"] == "needs_clarification"
    assert result["recommendation"]["review_status"] == "needs_clarification"
    assert result["selected_plan"] is None
    assert result["candidate_plans"] == []


def test_cli_output_is_repeatable():
    command = [sys.executable, "scripts/run_scenario.py", "--scenario", "SCN-003", "--mode", "mock"]
    first = subprocess.run(command, cwd=PROJECT_ROOT, capture_output=True, text=True, check=True)
    second = subprocess.run(command, cwd=PROJECT_ROOT, capture_output=True, text=True, check=True)

    assert first.stdout == second.stdout
    result = json.loads(first.stdout)
    assert result["verification"]["valid"]
