"""Frozen Track B gold-set schema and integrity helpers.

The dataset is additive: it never changes the demo corpus or the existing
retrieval/extraction evaluation inputs.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

TRACK_B_VERSION = "track_b_gold_v1.1"
TRACK_B_DIR = Path("data/eval/track_b")
CASES_FILE = "cases.jsonl"
MANIFEST_FILE = "manifest.json"

CASE_COUNT = 80
DEV_COUNT = 60
CONFIRM_COUNT = 20

GROUPS = (
    "canonical_scenario",
    "restatement",
    "inbound_persistence",
    "multi_turn",
    "authority_security",
    "intent_variant",
    "edge_case",
)

MODES = ("scenario", "inbound", "multi_turn")

SENTINEL_ANY = "__any__"

EXPECT_KEYS = {
    "primary_intent",
    "required_intents",
    "forbidden_intents",
    "event_type",
    "review_kind",
    "allowed_review_kinds",
    "routed_action",
    "allowed_routed_actions",
    "review_status",
    "allowed_review_statuses",
    "event_status",
    "selected_candidate_id",
    "verification_valid",
    "required_documents",
    "summary_contains",
    "question_contains",
    "processing_error",
    "queue_delta",
    "duplicate",
    "duplicate_first",
    "uncertainty_contains",
    "no_autonomous_action",
    "expected_facts",
    "expected_inferences",
    "plan",
    "outcome",
    "case",
    "market",
    "ack_status",
}


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def case_hash(case: dict) -> str:
    return sha256_text(canonical_json(case))


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_case(case: dict) -> list[str]:
    problems: list[str] = []
    required = ("case_id", "group", "split", "mode", "description", "expect")
    for key in required:
        if key not in case:
            problems.append(f"{case.get('case_id', '?')}: missing {key}")
    if problems:
        return problems

    if case["group"] not in GROUPS:
        problems.append(f"{case['case_id']}: unknown group {case['group']}")
    if case["split"] not in {"dev", "confirm"}:
        problems.append(f"{case['case_id']}: bad split {case['split']}")
    if case["mode"] not in MODES:
        problems.append(f"{case['case_id']}: bad mode {case['mode']}")

    expect = case["expect"]
    unknown = set(expect) - EXPECT_KEYS
    if unknown:
        problems.append(f"{case['case_id']}: unknown expect keys {sorted(unknown)}")
    if expect.get("no_autonomous_action") is not True:
        problems.append(f"{case['case_id']}: every case must require no_autonomous_action")
    if "selected_candidate_id" in expect and not isinstance(expect["selected_candidate_id"], (str, type(None))):
        problems.append(f"{case['case_id']}: selected_candidate_id must be a string or null")
    if "queue_delta" in expect and not isinstance(expect["queue_delta"], int):
        problems.append(f"{case['case_id']}: queue_delta must be an integer")
    if case["mode"] == "multi_turn":
        turns = case.get("turns")
        if not isinstance(turns, list) or len(turns) < 2:
            problems.append(f"{case['case_id']}: multi_turn needs at least two turns")
        elif any("text" not in turn or "expect" not in turn for turn in turns):
            problems.append(f"{case['case_id']}: every turn needs text and expect")
    elif "turns" in case:
        problems.append(f"{case['case_id']}: only multi_turn cases may define turns")
    if case["mode"] in {"scenario", "inbound"} and not isinstance(case.get("message"), dict):
        problems.append(f"{case['case_id']}: {case['mode']} cases need a message object")
    if not case.get("scenario_id") and case["mode"] == "scenario":
        problems.append(f"{case['case_id']}: scenario mode requires scenario_id")
    return problems


def load_cases(path: Path) -> list[dict]:
    cases: list[dict] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            case = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_number}: invalid JSON: {exc}") from exc
        problems = validate_case(case)
        if problems:
            raise ValueError("; ".join(problems))
        cases.append(case)
    return cases


def validate_dataset(cases: list[dict]) -> list[str]:
    problems: list[str] = []
    if len(cases) != CASE_COUNT:
        problems.append(f"expected {CASE_COUNT} cases, found {len(cases)}")
    expected_ids = [f"TB-{number:03d}" for number in range(1, CASE_COUNT + 1)]
    actual_ids = [case["case_id"] for case in cases]
    if actual_ids != expected_ids:
        problems.append("case ids are not the frozen TB-001..TB-080 sequence")
    splits = {"dev": 0, "confirm": 0}
    groups = {group: 0 for group in GROUPS}
    for case in cases:
        splits[case["split"]] += 1
        groups[case["group"]] += 1
    if splits["dev"] != DEV_COUNT or splits["confirm"] != CONFIRM_COUNT:
        problems.append(f"split counts are {splits}, expected {DEV_COUNT}/{CONFIRM_COUNT}")
    for group, expected in {
        "canonical_scenario": 15,
        "restatement": 15,
        "inbound_persistence": 15,
        "multi_turn": 10,
        "authority_security": 10,
        "intent_variant": 10,
        "edge_case": 5,
    }.items():
        if groups[group] != expected:
            problems.append(f"group {group} has {groups[group]} cases, expected {expected}")
    return problems
