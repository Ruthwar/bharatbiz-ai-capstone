"""Isolated end-to-end evaluation for the frozen Track B gold set.

Every case uses fresh in-memory intake and retail stores. The runner never
approves a review, executes a business action, or touches the demo databases.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from app.extraction.rules import RulesExtractor
from app.evaluation.track_b_schema import (
    CASES_FILE,
    MANIFEST_FILE,
    SENTINEL_ANY,
    TRACK_B_DIR,
    TRACK_B_VERSION,
    case_hash,
    load_cases,
    validate_dataset,
)
from app.orchestration.inbound import process_inbound
from app.orchestration.review import build_review_context
from app.orchestration.workflow import process_message
from app.scenarios.registry import get_scenario
from app.scenarios.service import run_scenario
from app.schemas.contracts import MessageSubmission, SenderRef
from app.store.ledger import InboundLedger
from app.store.retail import RetailStore

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CASES_PATH = PROJECT_ROOT / TRACK_B_DIR / CASES_FILE
DEFAULT_MANIFEST_PATH = PROJECT_ROOT / TRACK_B_DIR / MANIFEST_FILE

EXECUTION_KEYS = (
    "executed",
    "auto_approved",
    "auto_executed",
    "purchase_order_created",
    "payment_sent",
    "discount_applied",
    "quarantine_executed",
    "return_executed",
    "dispatch_executed",
    "outbound_message_sent",
)
SAFE_REVIEW_STATUSES = {"pending_review", "needs_clarification", "rejected"}

CHECK_LABELS = {
    "primary_intent": "intent_miss",
    "required_intents": "intent_miss",
    "forbidden_intents": "intent_leak",
    "event_type": "event_type_miss",
    "review_kind": "review_kind_miss",
    "allowed_review_kinds": "review_kind_miss",
    "routed_action": "routing_miss",
    "allowed_routed_actions": "routing_miss",
    "review_status": "status_miss",
    "allowed_review_statuses": "status_miss",
    "event_status": "status_miss",
    "selected_candidate_id": "selection_miss",
    "verification_valid": "verification_fail",
    "required_documents": "citation_miss",
    "summary_contains": "summary_miss",
    "question_contains": "clarification_miss",
    "processing_error": "error_handling_miss",
    "queue_delta": "review_queue_miss",
    "duplicate": "dedup_miss",
    "duplicate_first": "dedup_miss",
    "uncertainty_contains": "uncertainty_miss",
    "expected_facts": "fact_miss",
    "expected_inferences": "fact_miss",
    "plan": "planning_miss",
    "outcome": "outcome_miss",
    "case": "case_miss",
    "market": "market_miss",
    "ack_status": "ack_miss",
    "no_autonomous_action": "autonomy_violation",
    "no_exception": "exception",
}


def _safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _result(payload: dict) -> dict:
    nested = payload.get("result")
    return nested if isinstance(nested, dict) else payload


def _template_message():
    return get_scenario("SCN-001").message


def _build_message(case: dict, override: dict | None = None, *, turn_index: int = 0) -> MessageSubmission:
    fixture = get_scenario(case["scenario_id"]) if case.get("scenario_id") else None
    base = fixture.message if fixture else _template_message()
    override = override or case.get("message") or {}
    sender = base.sender
    return MessageSubmission(
        message_id=override.get("message_id", f"TB-{case['case_id']}-{turn_index or 1}"),
        source_type=base.source_type,
        text=override.get("text", base.text),
        observed_at=base.observed_at,
        language=override.get("language", base.language),
        consent_status=base.consent_status,
        state_version=override.get("state_version", base.state_version),
        conversation_id=f"track-b-{case['case_id']}",
        sender=SenderRef(
            party_type=override.get("sender_type", sender.party_type if sender else "unknown"),
            party_id=override.get("sender_id", sender.party_id if sender else None),
            channel=sender.channel if sender else "api",
        ),
    )


def _fixture_for(case: dict, message: MessageSubmission | None = None):
    if not case.get("scenario_id"):
        return None
    fixture = get_scenario(case["scenario_id"])
    if message is None:
        return fixture
    return fixture.model_copy(update={"message": message})


def _invoke(case: dict, message: MessageSubmission, ledger: InboundLedger, store: RetailStore) -> dict:
    fixture = _fixture_for(case, message if case["mode"] == "scenario" or case.get("message") else None)
    # The gold set must not change with the environment's model configuration.
    extractor = RulesExtractor()
    if case["mode"] == "scenario":
        if case.get("message"):
            return process_message(
                message, scenario=fixture, decision_mode="deterministic", extractor=extractor
            )
        return run_scenario(case["scenario_id"], decision_mode="deterministic", extractor=extractor)
    return process_inbound(
        message,
        ledger=ledger,
        retail_store=store,
        scenario=fixture,
        decision_mode="deterministic",
        extractor=extractor,
    )


def execute_case(case: dict) -> dict:
    ledger = InboundLedger()
    store = RetailStore(":memory:")
    payloads: list[dict] = []
    started = time.perf_counter()
    try:
        if case["mode"] == "multi_turn":
            for index, turn in enumerate(case["turns"], start=1):
                override = {
                    "text": turn["text"],
                    "message_id": f"TB-{case['case_id']}-{index}",
                }
                if "sender_id" in turn:
                    override["sender_id"] = turn["sender_id"]
                message = _build_message(case, override, turn_index=index)
                payloads.append(_invoke(case, message, ledger, store))
        else:
            message = _build_message(case)
            payloads.append(_invoke(case, message, ledger, store))
            if case.get("repeat", 1) > 1:
                for repeat_index in range(2, case["repeat"] + 1):
                    repeat = message.model_copy(update={"message_id": message.message_id})
                    payloads.append(_invoke(case, repeat, ledger, store))
        error = None
    except Exception as exc:  # noqa: BLE001 - failures are evidence, not crashes
        error = f"{type(exc).__name__}: {exc}"
        payloads = []
    duration_ms = (time.perf_counter() - started) * 1000
    return {
        "case": case,
        "payloads": payloads,
        "ledger": ledger,
        "store": store,
        "error": error,
        "duration_ms": duration_ms,
    }


def _check(name: str, passed: bool, expected: Any, actual: Any) -> dict:
    return {
        "name": name,
        "passed": bool(passed),
        "expected": _safe(expected),
        "actual": _safe(actual),
        "label": CHECK_LABELS[name.rsplit(".", 1)[-1]],
    }


def _references(result: dict) -> tuple[list[str], str | None]:
    try:
        context = build_review_context(result)
    except Exception as exc:  # noqa: BLE001
        return [], f"{type(exc).__name__}: {exc}"
    document_ids: list[str] = []
    for reference in context.get("references") or []:
        document_id = reference.get("document_id")
        if document_id and document_id not in document_ids:
            document_ids.append(document_id)
    return document_ids, None


def _subset_matches(expected: dict, actual: dict) -> tuple[bool, dict]:
    mismatches: dict = {}
    for key, value in expected.items():
        if str(actual.get(key)) != str(value):
            mismatches[key] = {"expected": value, "actual": actual.get(key)}
    return not mismatches, mismatches


def _autonomy_violations(payload: dict, result: dict) -> list[str]:
    violations: list[str] = []
    recommendation = result.get("recommendation") or {}
    if recommendation and recommendation.get("human_approval_required") is not True:
        violations.append("recommendation does not require human approval")
    status = recommendation.get("review_status")
    if status and status not in SAFE_REVIEW_STATUSES:
        violations.append(f"review status is {status}")

    def walk(value: Any, path: str = "") -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                location = f"{path}.{key}" if path else key
                if key in EXECUTION_KEYS and item:
                    violations.append(f"{location} is truthy")
                if key == "review_status" and item == "approved":
                    violations.append(f"{location} is approved")
                if key == "decision" and isinstance(item, dict) and item.get("status") in {
                    "approved",
                    "executed",
                }:
                    violations.append(f"{location}.status is {item.get('status')}")
                walk(item, location)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                walk(item, f"{path}[{index}]")

    walk(payload, "payload")
    return violations


def grade_expect(
    expect: dict,
    payload: dict,
    *,
    ledger: InboundLedger | None = None,
    prefix: str = "",
) -> list[dict]:
    result = _result(payload)
    event = result.get("event") or {}
    recommendation = result.get("recommendation") or {}
    selected_plan = result.get("selected_plan") or {}
    advisory_context = result.get("advisory_context") or {}
    case_context = result.get("case_context") or {}
    market_context = result.get("market_context") or {}
    checks: list[dict] = []

    def name(key: str) -> str:
        return f"{prefix}{key}" if not prefix else f"{prefix}{key}"

    intents = [item.get("intent") for item in event.get("intents") or [] if item.get("intent")]
    if "primary_intent" in expect:
        checks.append(_check(name("primary_intent"), bool(intents) and intents[0] == expect["primary_intent"], expect["primary_intent"], intents[0] if intents else None))
    if "required_intents" in expect:
        missing = [intent for intent in expect["required_intents"] if intent not in intents]
        checks.append(_check(name("required_intents"), not missing, expect["required_intents"], intents))
    if "forbidden_intents" in expect:
        leaked = [intent for intent in expect["forbidden_intents"] if intent in intents]
        checks.append(_check(name("forbidden_intents"), not leaked, expect["forbidden_intents"], intents))
    if "event_type" in expect:
        checks.append(_check(name("event_type"), event.get("event_type") == expect["event_type"], expect["event_type"], event.get("event_type")))
    if "review_kind" in expect:
        checks.append(_check(name("review_kind"), result.get("review_kind") == expect["review_kind"], expect["review_kind"], result.get("review_kind")))
    if "allowed_review_kinds" in expect:
        checks.append(_check(name("allowed_review_kinds"), result.get("review_kind") in expect["allowed_review_kinds"], expect["allowed_review_kinds"], result.get("review_kind")))
    if "routed_action" in expect:
        checks.append(_check(name("routed_action"), payload.get("routed_action") == expect["routed_action"], expect["routed_action"], payload.get("routed_action")))
    if "allowed_routed_actions" in expect:
        checks.append(_check(name("allowed_routed_actions"), payload.get("routed_action") in expect["allowed_routed_actions"], expect["allowed_routed_actions"], payload.get("routed_action")))
    if "review_status" in expect:
        actual = recommendation.get("review_status") if recommendation else None
        checks.append(_check(name("review_status"), actual == expect["review_status"], expect["review_status"], actual))
    if "allowed_review_statuses" in expect:
        actual = recommendation.get("review_status") if recommendation else None
        checks.append(_check(name("allowed_review_statuses"), actual in expect["allowed_review_statuses"], expect["allowed_review_statuses"], actual))
    if "event_status" in expect:
        checks.append(_check(name("event_status"), event.get("status") == expect["event_status"], expect["event_status"], event.get("status")))
    if "selected_candidate_id" in expect:
        actual = selected_plan.get("candidate_id") if selected_plan else None
        expected = expect["selected_candidate_id"]
        passed = actual is not None if expected == SENTINEL_ANY else actual == expected
        checks.append(_check(name("selected_candidate_id"), passed, expected, actual))
    if "verification_valid" in expect:
        verification = result.get("verification")
        actual = verification.get("valid") if verification else None
        checks.append(_check(name("verification_valid"), actual == expect["verification_valid"], expect["verification_valid"], actual))
    if "required_documents" in expect:
        document_ids, error = _references(result)
        missing = [doc for doc in expect["required_documents"] if doc not in document_ids]
        checks.append(_check(name("required_documents"), not missing and not error, expect["required_documents"], {"documents": document_ids, "error": error}))
    if "summary_contains" in expect:
        summary = recommendation.get("summary") or ""
        missing = [text for text in expect["summary_contains"] if text not in summary]
        checks.append(_check(name("summary_contains"), not missing, expect["summary_contains"], summary))
    if "question_contains" in expect:
        question = payload.get("question") or ""
        checks.append(_check(name("question_contains"), expect["question_contains"] in question, expect["question_contains"], question))
    if "processing_error" in expect:
        checks.append(_check(name("processing_error"), payload.get("processing_error") == expect["processing_error"], expect["processing_error"], payload.get("processing_error")))
    if "queue_delta" in expect:
        if ledger is None:
            checks.append(_check(name("queue_delta"), False, expect["queue_delta"], "no isolated ledger"))
        else:
            actual = len(ledger.pending_reviews())
            checks.append(_check(name("queue_delta"), actual == expect["queue_delta"], expect["queue_delta"], actual))
    if "duplicate" in expect:
        checks.append(_check(name("duplicate"), payload.get("duplicate") == expect["duplicate"], expect["duplicate"], payload.get("duplicate")))
    if "uncertainty_contains" in expect:
        uncertainties = " ".join(str(item) for item in event.get("uncertainties") or [])
        checks.append(_check(name("uncertainty_contains"), expect["uncertainty_contains"] in uncertainties, expect["uncertainty_contains"], uncertainties))
    if "expected_facts" in expect:
        facts: dict[str, list[str]] = {}
        for fact in event.get("extracted_facts") or []:
            facts.setdefault(fact.get("field"), []).append(fact.get("value"))
        missing = {
            field: value
            for field, value in expect["expected_facts"].items()
            if str(value) not in [str(item) for item in facts.get(field, [])]
        }
        checks.append(_check(name("expected_facts"), not missing, expect["expected_facts"], {key: value for key, value in facts.items() if key in expect["expected_facts"]}))
    if "expected_inferences" in expect:
        passed, mismatches = _subset_matches(expect["expected_inferences"], event.get("inferences") or {})
        checks.append(_check(name("expected_inferences"), passed, expect["expected_inferences"], mismatches or event.get("inferences")))
    if "plan" in expect:
        passed, mismatches = _subset_matches(expect["plan"], selected_plan)
        checks.append(_check(name("plan"), passed, expect["plan"], mismatches or {key: selected_plan.get(key) for key in expect["plan"]}))
    if "outcome" in expect:
        passed, mismatches = _subset_matches(expect["outcome"], advisory_context.get("outcome") or {})
        checks.append(_check(name("outcome"), passed, expect["outcome"], mismatches or advisory_context.get("outcome")))
    if "case" in expect:
        passed, mismatches = _subset_matches(expect["case"], case_context)
        checks.append(_check(name("case"), passed, expect["case"], mismatches or case_context))
    if "market" in expect:
        passed, mismatches = _subset_matches(expect["market"], market_context)
        checks.append(_check(name("market"), passed, expect["market"], mismatches or market_context))
    if "ack_status" in expect:
        ack = payload.get("ack") or {}
        checks.append(_check(name("ack_status"), ack.get("status") == expect["ack_status"], expect["ack_status"], ack.get("status")))
    if expect.get("no_autonomous_action"):
        violations = _autonomy_violations(payload, result)
        checks.append(_check(name("no_autonomous_action"), not violations, "no executed business action", violations))
    return checks


def grade_case(executed: dict) -> dict:
    case = executed["case"]
    payloads = executed["payloads"]
    checks: list[dict] = []
    if executed["error"]:
        checks.append(_check("no_exception", False, "no exception", executed["error"]))
    else:
        checks.append(_check("no_exception", True, "no exception", None))
        if case["mode"] == "multi_turn":
            for index, turn in enumerate(case["turns"], start=1):
                checks.extend(grade_expect(turn.get("expect") or {}, payloads[index - 1], prefix=f"turn_{index}."))
        final = payloads[-1] if payloads else {}
        checks.extend(grade_expect(case["expect"], final, ledger=executed["ledger"]))
        if case.get("repeat", 1) > 1 and "duplicate_first" in case["expect"]:
            first = payloads[0].get("duplicate") if payloads else None
            checks.append(_check("duplicate_first", first == case["expect"]["duplicate_first"], case["expect"]["duplicate_first"], first))
    failures = [check["label"] for check in checks if not check["passed"]]
    return {
        "case_id": case["case_id"],
        "group": case["group"],
        "split": case["split"],
        "description": case["description"],
        "passed": not failures,
        "failure_labels": sorted(set(failures)),
        "checks": checks,
        "duration_ms": round(executed["duration_ms"], 2),
        "exception": executed["error"],
    }


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def run_track_b_evaluation(
    *,
    cases_path: Path | None = None,
    case_ids: list[str] | None = None,
    split: str | None = None,
    group: str | None = None,
    progress: Callable[[dict], None] | None = None,
) -> dict:
    cases_path = cases_path or DEFAULT_CASES_PATH
    cases = load_cases(cases_path)
    problems = validate_dataset(cases)
    if problems:
        raise ValueError("Track B dataset is invalid: " + "; ".join(problems))
    if case_ids:
        selected = set(case_ids)
        cases = [case for case in cases if case["case_id"] in selected]
        missing = selected - {case["case_id"] for case in cases}
        if missing:
            raise ValueError(f"unknown case ids: {sorted(missing)}")
    if split:
        cases = [case for case in cases if case["split"] == split]
    if group:
        cases = [case for case in cases if case["group"] == group]

    if progress:
        progress(
            {
                "step": "dataset_loaded",
                "title": f"Loaded {len(cases)} frozen gold cases",
                "current": 0,
                "total": len(cases),
                "detail": f"Dataset {TRACK_B_VERSION}; every case runs in isolated intake and retail stores.",
            }
        )
    rows = []
    for position, case in enumerate(cases, start=1):
        row = grade_case(execute_case(case))
        rows.append(row)
        if progress:
            progress(
                {
                    "step": "case_completed",
                    "title": f"{row['case_id']}: {'passed' if row['passed'] else 'failed'}",
                    "current": position,
                    "total": len(cases),
                    "outcome": "passed" if row["passed"] else "failed",
                    "detail": row["description"],
                }
            )
    passed = [row for row in rows if row["passed"]]
    failed = [row for row in rows if not row["passed"]]
    check_totals: dict[str, dict] = {}
    label_counts: dict[str, int] = {}
    for row in rows:
        for check in row["checks"]:
            bucket = check_totals.setdefault(check["name"], {"passed": 0, "failed": 0})
            bucket["passed" if check["passed"] else "failed"] += 1
        for label in row["failure_labels"]:
            label_counts[label] = label_counts.get(label, 0) + 1

    def group_summary(subset: list[dict]) -> dict:
        return {
            "cases": len(subset),
            "passed": sum(1 for row in subset if row["passed"]),
            "failed": sum(1 for row in subset if not row["passed"]),
            "pass_rate": round(sum(1 for row in subset if row["passed"]) / len(subset), 4) if subset else 0.0,
        }

    by_group = {name: group_summary([row for row in rows if row["group"] == name]) for name in sorted({row["group"] for row in rows})}
    by_split = {name: group_summary([row for row in rows if row["split"] == name]) for name in sorted({row["split"] for row in rows})}
    durations = [row["duration_ms"] for row in rows]
    manifest_path = cases_path.parent / MANIFEST_FILE
    dataset_sha = None
    if manifest_path.exists():
        dataset_sha = json.loads(manifest_path.read_text(encoding="utf-8")).get("dataset_sha256")

    return {
        "version": TRACK_B_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "decision_mode": "deterministic",
        "dataset_sha256": dataset_sha,
        "case_hash": {row["case_id"]: case_hash(next(case for case in cases if case["case_id"] == row["case_id"])) for row in rows},
        "summary": {
            **group_summary(rows),
            "by_group": by_group,
            "by_split": by_split,
            "failure_labels": dict(sorted(label_counts.items())),
            "checks": {name: {**values, "total": values["passed"] + values["failed"]} for name, values in sorted(check_totals.items())},
            "exceptions": sum(1 for row in rows if row["exception"]),
            "latency_ms_p50": round(_percentile(durations, 0.50), 2),
            "latency_ms_p95": round(_percentile(durations, 0.95), 2),
        },
        "rows": rows,
    }


def ensure_frozen_inputs(cases_path: Path | None = None) -> list[str]:
    """Return integrity problems without mutating any file."""
    cases_path = cases_path or DEFAULT_CASES_PATH
    manifest_path = cases_path.parent / MANIFEST_FILE
    if not cases_path.exists() or not manifest_path.exists():
        return ["frozen cases or manifest missing"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    problems: list[str] = []
    cases = load_cases(cases_path)
    if manifest.get("dataset_sha256") != __import__("hashlib").sha256(cases_path.read_bytes()).hexdigest():
        problems.append("dataset sha256 does not match manifest")
    for case in cases:
        if manifest.get("case_hashes", {}).get(case["case_id"]) != case_hash(case):
            problems.append(f"{case['case_id']} hash does not match manifest")
    return problems
