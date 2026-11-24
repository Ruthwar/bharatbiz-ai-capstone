from decimal import Decimal

import pytest

from app.optimization.context import build_planning_view
from app.orchestration.review import build_review_context
from app.orchestration.workflow import process_message
from app.scenarios.contracts import ScenarioOverlays
from app.scenarios.registry import get_scenario, list_scenarios, validate_scenario
from app.scenarios.service import run_scenario
from app.schemas.contracts import CandidatePlan
from app.state import load_business_state
from app.store.ledger import SqliteLedger
from app.verification.checks import verify_scenario_plan

OPERATIONAL_IDS = ("SCN-001", "SCN-002", "SCN-003", "SCN-004", "SCN-005", "SCN-008")


def test_scenario_registry_is_complete_and_valid(state):
    fixtures = list_scenarios()
    assert [fixture.scenario_id for fixture in fixtures] == [f"SCN-{index:03d}" for index in range(1, 16)]
    for fixture in fixtures:
        validate_scenario(fixture, state)


@pytest.mark.parametrize("scenario_id", OPERATIONAL_IDS)
def test_operational_fixture_expectations(scenario_id):
    fixture = get_scenario(scenario_id)
    result = run_scenario(scenario_id)
    selected = result["selected_plan"]
    expected = fixture.expected

    assert result["review_kind"] == "operational_plan"
    assert result["recommendation"]["review_status"] == expected["review_status"]
    assert result["verification"]["valid"] is expected["verification_valid"]
    assert selected["candidate_id"] == expected["selected_candidate_id"]
    for field in ("requested_units", "fulfilled_units", "late_units", "unmet_units"):
        if field in expected:
            assert selected[f"total_{field}" if field == "requested_units" else field] == expected[field]
    if "procurement_units" in expected:
        assert selected["supplier_option"]["quantity_units"] == expected["procurement_units"]
    if "total_cost_rupees" in expected:
        assert selected["total_cost_rupees"] == expected["total_cost_rupees"]
    if "scenario_arrival_date" in expected:
        assert selected["supplier_option"]["scenario_arrival_date"] == expected["scenario_arrival_date"]
    if "ending_cash_rupees" in expected:
        assert selected["cash_projection"]["ending_cash_rupees"] == expected["ending_cash_rupees"]
    if "headroom_rupees" in expected:
        assert selected["cash_projection"]["headroom_rupees"] == expected["headroom_rupees"]
    for field in ("scenario_usable_units", "book_on_hand_units", "counted_on_hand_units"):
        if field in expected:
            assert result["scenario_view"][field] == expected[field]
    if "counterfactual" in expected:
        counterfactual = next(row for row in result["counterfactuals"] if row["name"] == expected["counterfactual"])
        counter_selected = counterfactual["selected_plan"]
        assert counter_selected["candidate_id"] == expected["counterfactual_selected_candidate_id"]
        assert counterfactual["verification"]["valid"]
        if "counterfactual_procurement_units" in expected:
            assert counter_selected["supplier_option"]["quantity_units"] == expected["counterfactual_procurement_units"]


def test_scn003_canonical_result_is_preserved():
    selected = run_scenario("SCN-003")["selected_plan"]
    assert selected["total_requested_units"] == 102
    assert selected["fulfilled_units"] == 102
    assert selected["late_units"] == 28
    assert selected["unmet_units"] == 0
    assert selected["candidate_id"] == "supplier-SUP-002"
    assert selected["supplier_option"]["quantity_units"] == 46
    assert selected["total_cost_rupees"] == "4876.46"
    assert selected["cash_projection"]["ending_cash_rupees"] == "245123.54"
    assert selected["cash_projection"]["headroom_rupees"] == "195123.54"


def test_demand_spike_rounds_each_order_line():
    result = run_scenario("SCN-002")
    orders = result["agent_results"][1]["proposal"]["affected_orders"]
    assert [row["quantity_units"] for row in orders] == [5, 18, 13, 39, 37]
    assert sum(row["quantity_units"] for row in orders) == 112


def test_limited_cash_exclusions_and_counterfactual_are_visible():
    result = run_scenario("SCN-004")
    assert any("cash_buffer_breached" in row["reasons"] for row in result["excluded_candidates"])
    counterfactual = result["counterfactuals"][0]
    assert counterfactual["selected_plan"]["cash_projection"]["ending_cash_rupees"] == "76790.06"
    combined = run_scenario("SCN-008")["counterfactuals"][0]["selected_plan"]
    assert combined["late_units"] == 81
    assert combined["total_cost_rupees"] == "10385.10"
    assert combined["cash_projection"]["ending_cash_rupees"] == "69614.90"


def test_stock_discrepancy_preserves_book_and_unverified_count():
    result = run_scenario("SCN-005")
    assert result["scenario_view"]["book_on_hand_units"] == 63
    assert result["scenario_view"]["counted_on_hand_units"] == 48
    assert any("unverified" in row for row in result["recommendation"]["assumptions"])


def test_operational_overlays_do_not_mutate_base_state():
    before = load_business_state().model_dump(mode="json")
    for scenario_id in ("SCN-002", "SCN-003", "SCN-005", "SCN-008"):
        run_scenario(scenario_id)
    assert load_business_state().model_dump(mode="json") == before


def test_complaint_requires_order_reference_then_accepts_a_valid_followup():
    fixture = get_scenario("SCN-006")
    result = process_message(fixture.message, scenario=fixture)
    assert result["case_context"]["matched_order_count"] == 2
    assert result["case_context"]["clarification_slot"] == "order_reference"
    assert result["selected_plan"] is None
    assert result["recommendation"]["review_status"] == "needs_clarification"

    followup = fixture.message.model_copy(update={"text": fixture.message.text + " It is ORD-0016."})
    resolved = process_message(followup, scenario=fixture)
    assert resolved["case_context"]["matched_order_count"] == 1
    assert resolved["case_context"]["matched_orders"][0]["order_id"] == "ORD-0016"
    assert resolved["recommendation"]["review_status"] == "pending_review"
    assert not resolved["case_context"]["operational_action_executed"]


def test_competitor_corroboration_counts_distinct_reporters():
    result = run_scenario("SCN-007")
    context = result["market_context"]
    assert context["unique_observation_count"] == 2
    assert context["distinct_reporter_count"] == 2
    assert context["corroboration"] == "corroborated_unverified"
    assert context["verification_status"] == "reported_unverified"
    assert result["selected_plan"] is None


def test_smaller_pack_request_does_not_invent_availability_or_assortment_change():
    context = run_scenario("SCN-009")["market_context"]
    assert context["distinct_retailer_count"] == 3
    assert context["reported_request_count"] == 9
    assert context["catalogue_match"] is False
    assert context["matched_sku_id"] is None
    assert context["assortment_changed"] is False


def test_non_plan_review_persists_in_sqlite_without_executing_an_action():
    ledger = SqliteLedger(":memory:")
    result = run_scenario("SCN-007", persist=True, ledger=ledger)
    pending = ledger.pending_reviews()
    assert len(pending) == 1
    assert pending[0]["why"]["review_kind"] == "market_signal_review"
    assert pending[0]["why"]["market_context"]["distinct_reporter_count"] == 2
    assert result["inbound"]["routed_action"] == "competitor_observation_planning"
    ledger.decide(pending[0]["event_id"], "approve", "test-reviewer")
    assert ledger.pending_reviews() == []
    assert result["market_context"]["operational_action_executed"] is False


def test_corrupted_plan_fails_independent_reconstruction(state):
    fixture = get_scenario("SCN-003")
    result = run_scenario("SCN-003")
    corrupted = CandidatePlan.model_validate(result["selected_plan"]).model_copy(deep=True)
    corrupted.allocations[0].fulfilled_units += 1
    verification = verify_scenario_plan(state, corrupted, fixture.overlays, fixture.target_sku_id)
    assert not verification.valid
    assert f"fulfilment_split_mismatch:{corrupted.allocations[0].order_id}" in verification.violations


def test_physical_count_below_reserved_stock_is_rejected(state):
    with pytest.raises(ValueError, match="reserved"):
        build_planning_view(state, "SKU-006", ScenarioOverlays(physical_count_delta=-60))


def test_cash_projection_rejects_tampered_daily_schedule(state):
    fixture = get_scenario("SCN-004")
    result = run_scenario("SCN-004")
    counterfactual = result["counterfactuals"][0]
    corrupted = CandidatePlan.model_validate(counterfactual["selected_plan"]).model_copy(deep=True)
    corrupted.cash_projection.daily_schedule[0].receipts_rupees += Decimal("1.00")
    verification = verify_scenario_plan(
        state,
        corrupted,
        fixture.overlays,
        fixture.target_sku_id,
        receipt_timing="on_time",
    )
    assert not verification.valid
    assert "cash_schedule_mismatch" in verification.violations


ADVISORY_EXPECTATIONS = {
    "SCN-010": {
        "kind": "credit_review",
        "metrics": {"Past due": "₹57,448.23", "New order": "₹4,620.00", "Limit headroom": "₹-12,068.23"},
        "warning": "hold limit breach",
        "policy": "POL-RCM-007",
    },
    "SCN-011": {
        "kind": "scheme_claim_review",
        "metrics": {"Claimed": "10%", "Approved": "7.50%", "Checks failed": "2"},
        "warning": "claim mismatch",
        "policy": "POL-PRC-005",
    },
    "SCN-012": {
        "kind": "delivery_discrepancy_review",
        "metrics": {"Net shortfall": "16 litres", "Damaged": "5", "Wrong item": "3"},
        "warning": "Supplier claim candidate: 16 litres",
        "policy": "POL-RCM-007",
    },
    "SCN-013": {
        "kind": "recall_review",
        "metrics": {"Free to hold": "110", "Open orders": "4", "Batch status": "quality hold"},
        "warning": "Quality hold recommended",
        "policy": "POL-STK-007",
    },
    "SCN-014": {
        "kind": "expiry_review",
        "metrics": {"Days to expiry": "9", "Return window": "14 days", "Open demand": "43"},
        "warning": "Short-dated stock",
        "policy": "POL-STK-007",
    },
    "SCN-015": {
        "kind": "dispatch_review",
        "metrics": {"Capacity used": "26/40", "Deferred orders": "1", "Departure": "2026-11-24"},
        "warning": "Route capacity exceeded",
        "policy": "POL-SVC-009",
    },
}


@pytest.mark.parametrize("scenario_id", ADVISORY_EXPECTATIONS)
def test_advisory_fixture_is_review_only_and_matches_expectations(scenario_id):
    fixture = get_scenario(scenario_id)
    result = run_scenario(scenario_id)
    expected = ADVISORY_EXPECTATIONS[scenario_id]
    advisory = result["advisory_context"]

    assert result["review_kind"] == expected["kind"]
    assert result["recommendation"]["review_status"] == "pending_review"
    assert result["recommendation"]["human_approval_required"] is True
    assert result["selected_plan"] is None
    assert result["candidate_plans"] == []
    assert result["verification"] is None
    assert "No credit, price, stock, dispatch or outbound-message action is executed." in result["recommendation"]["warnings"]
    assert {row["label"]: row["value"] for row in advisory["metrics"]} == expected["metrics"]
    for key, value in fixture.expected.items():
        if key in advisory["outcome"]:
            assert advisory["outcome"][key] == value
    assert any(expected["warning"] in warning for warning in result["recommendation"]["warnings"])

    context = build_review_context(result)
    assert context["review_kind"] == expected["kind"]
    assert expected["policy"] in {reference["document_id"] for reference in context["references"]}
    assert all(reference["relation"] == "reference" for reference in context["references"])
    assert any(step["title"] == "Policy rules listed, not applied" for step in context["decision_steps"])


@pytest.mark.parametrize(
    ("scenario_id", "event_type", "party_field"),
    [
        ("SCN-010", "credit_check", "retailer_id"),
        ("SCN-011", "scheme_claim", None),
        ("SCN-012", "delivery_discrepancy", None),
        ("SCN-013", "batch_recall", "supplier_id"),
        ("SCN-014", "short_dated_stock", None),
        ("SCN-015", "dispatch_planning", None),
    ],
)
def test_advisory_routing_uses_event_type_and_reported_party(scenario_id, event_type, party_field):
    result = run_scenario(scenario_id)
    assert result["event"]["event_type"] == event_type
    if party_field:
        facts = {fact["field"]: fact["value"] for fact in result["event"]["extracted_facts"]}
        assert facts[party_field] == get_scenario(scenario_id).message.sender.party_id


def test_advisory_rejects_wrong_sender_type():
    fixture = get_scenario("SCN-010")
    wrong_sender = fixture.message.model_copy(
        update={"sender": fixture.message.sender.model_copy(update={"party_type": "supplier", "party_id": "SUP-001"})}
    )
    result = process_message(wrong_sender, scenario=fixture)
    assert result["review_kind"] == "triage"
    assert result.get("recommendation") is None
    assert result.get("selected_plan") is None
    assert any("may only be reported by" in note for note in result["event"]["uncertainties"])


def test_advisory_scenarios_do_not_change_business_state():
    before = load_business_state().model_dump(mode="json")
    for scenario_id in ADVISORY_EXPECTATIONS:
        run_scenario(scenario_id)
    assert load_business_state().model_dump(mode="json") == before



DISPATCH_BEST = "opt-ORD-0001+ORD-0018"
DISPATCH_WORSE = "opt-ORD-0006"


def _dispatch_sections(result):
    return {section["title"]: section for section in result["advisory_context"]["sections"]}


def test_dispatch_deterministic_enumerates_every_feasible_plan():
    result = run_scenario("SCN-015")
    decision = result["decision"]
    options = result["advisory_context"]["options"]

    assert decision["mode"] == "deterministic"
    assert decision["status"] == "recommended"
    assert decision["option_id"] == DISPATCH_BEST
    assert decision["citations"] == []
    assert result["decision_mode_applied"] is True
    assert len(options) == 7
    assert result["advisory_context"]["outcome"]["selected_option_id"] == DISPATCH_BEST

    sections = _dispatch_sections(result)
    rows = sections["Options considered"]["rows"]
    assert [row["Option"] for row in rows][0] == "Load ORD-0001, ORD-0018"
    assert rows[0]["Result"] == "Selected"
    assert any(row["Result"].startswith("Rejected:") for row in rows)
    assert any(row["Result"].startswith("Infeasible: Exceeds capacity") for row in rows)
    assert sections["Decision rationale"]["rows"][0] == {"Field": "Mode", "Value": "Deterministic"}
    assert "No credit, price, stock, dispatch or outbound-message action is executed." in result["recommendation"]["warnings"]


def test_dispatch_deterministic_never_calls_the_model(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("deterministic mode must not call the LLM")

    monkeypatch.setattr("app.decision.selector._call_advisory_model", fail)
    result = run_scenario("SCN-015")
    assert result["decision"]["option_id"] == DISPATCH_BEST


def test_dispatch_policy_mode_confirms_the_best_supplied_option(monkeypatch):
    calls = {}

    def fake(event_context, options, infeasible, references, capacity_units, demand_units):
        calls["capacity"] = capacity_units
        calls["demand"] = demand_units
        calls["option_ids"] = [option["option_id"] for option in options]
        return (
            {
                "option_id": DISPATCH_BEST,
                "priority": "capacity_constraint",
                "citations": ["POL-SVC-009"],
                "abstain_reason": None,
            },
            "fake-model",
        )

    monkeypatch.setattr("app.decision.selector._call_advisory_model", fake)
    result = run_scenario("SCN-015", decision_mode="policy_grounded_llm")
    decision = result["decision"]

    assert calls == {"capacity": 40, "demand": 47, "option_ids": [option["option_id"] for option in result["advisory_context"]["options"]]}
    assert decision["mode"] == "policy_grounded_llm"
    assert decision["status"] == "recommended"
    assert decision["option_id"] == DISPATCH_BEST
    assert decision["citations"] == ["POL-SVC-009"]
    assert decision["model"] == "fake-model"
    assert result["decision_mode"] == "policy_grounded_llm"
    assert result["decision_mode_applied"] is True
    assert result["advisory_context"]["outcome"]["decision_status"] == "recommended"
    assert result["advisory_context"]["sections"][-1]["rows"][0] == {"Field": "Mode", "Value": "Policy Grounded Llm"}

    context = build_review_context(result)
    assert {"document_id": "POL-SVC-009", "relation": "cited"}.items() <= next(
        reference for reference in context["references"] if reference["document_id"] == "POL-SVC-009"
    ).items()
    policy_step = next(step for step in context["decision_steps"] if step["title"] == "Policy rules checked")
    assert "grounded the selection" in policy_step["detail"]


def test_dispatch_policy_mode_abstains_without_falling_back(monkeypatch):
    monkeypatch.setattr(
        "app.decision.selector._call_advisory_model",
        lambda *args, **kwargs: (
            {"option_id": None, "priority": None, "citations": [], "abstain_reason": "Rules conflict on priority."},
            "fake-model",
        ),
    )
    result = run_scenario("SCN-015", decision_mode="policy_grounded_llm")

    assert result["decision"]["status"] == "abstained"
    assert result["decision"]["option_id"] is None
    assert "Rules conflict on priority." in result["decision"]["abstain_reason"]
    assert result["advisory_context"]["outcome"]["selected_option_id"] is None
    assert result["advisory_context"]["outcome"]["decision_status"] == "abstained"
    assert result["recommendation"]["review_status"] == "needs_clarification"
    assert len(result["advisory_context"]["options"]) == 7
    assert "did not select a plan" in result["advisory_context"]["operator_summary"]
    assert any(step["status"] == "blocked" for step in result["advisory_context"]["decision_steps"])
    assert "No credit, price, stock, dispatch or outbound-message action is executed." in result["recommendation"]["warnings"]


@pytest.mark.parametrize(
    ("parsed", "reason"),
    [
        (
            {"option_id": DISPATCH_BEST, "priority": "service_continuity", "citations": ["POL-FAKE-999"]},
            "unsupported policy citations",
        ),
        (
            {"option_id": DISPATCH_WORSE, "priority": "service_continuity", "citations": ["POL-SVC-009"]},
            "defers an earlier promise",
        ),
        (
            {"option_id": DISPATCH_BEST, "priority": "no_alternative", "citations": ["POL-SVC-009"]},
            "claimed no alternative",
        ),
    ],
)
def test_dispatch_policy_mode_rejects_invalid_model_choices(monkeypatch, parsed, reason):
    monkeypatch.setattr(
        "app.decision.selector._call_advisory_model", lambda *args, **kwargs: (parsed, "fake-model")
    )
    result = run_scenario("SCN-015", decision_mode="policy_grounded_llm")
    assert result["decision"]["status"] == "abstained"
    assert result["decision"]["option_id"] is None
    assert reason in result["decision"]["abstain_reason"]


CREDIT_HOLD = "opt-hold-new-order"
CREDIT_PAUSE = "opt-hold-all-orders"
CREDIT_ACCEPT = "opt-accept-order"
RECALL_HOLD = "opt-quarantine-batch"


def _review_sections(result):
    return {section["title"]: section for section in result["advisory_context"]["sections"]}


def test_credit_deterministic_compares_hold_outcomes():
    result = run_scenario("SCN-010")
    decision = result["decision"]
    options = result["advisory_context"]["options"]

    assert decision["mode"] == "deterministic"
    assert decision["status"] == "recommended"
    assert decision["option_id"] == CREDIT_HOLD
    assert decision["citations"] == []
    assert result["decision_mode_applied"] is True
    assert [option["option_id"] for option in options] == [CREDIT_HOLD, CREDIT_PAUSE]
    assert result["advisory_context"]["outcome"]["selected_option_id"] == CREDIT_HOLD
    assert result["advisory_context"]["outcome"]["decision_status"] == "recommended"

    rows = _review_sections(result)["Options considered"]["rows"]
    assert rows[0] == {
        "Option": "Hold the new order for a human credit decision",
        "Effect": "No order is accepted and nothing is sent to RET-016; every existing order keeps its current status.",
        "Result": "Selected",
    }
    assert rows[1]["Result"].startswith("Rejected: Does not reduce the ₹12,068.23 breach")
    assert rows[2]["Result"] == "Infeasible: Exceeds the ₹50,000.00 credit limit by ₹12,068.23."
    assert _review_sections(result)["Decision rationale"]["rows"][0] == {
        "Field": "Mode", "Value": "Deterministic"
    }
    rationale_rows = _review_sections(result)["Decision rationale"]["rows"]
    assert {"Field": "Decided by", "Value": "A fixed rule (no model called)"} in rationale_rows
    assert {"Field": "Role of the policies", "Value": "Reference only — they did not affect the choice."} in rationale_rows
    summary = result["advisory_context"]["operator_summary"]
    assert "No model was called and no policy passage was read" in summary

    context = build_review_context(result)
    assert context["references"]
    assert all(reference["relation"] == "reference" for reference in context["references"])
    policy_step = next(step for step in context["decision_steps"] if step["title"].startswith("Policy rules"))
    assert policy_step["title"] == "Policy rules listed, not applied"
    assert "never reads them" in policy_step["detail"]


def test_recall_deterministic_confirms_quarantine():
    result = run_scenario("SCN-013")
    decision = result["decision"]

    assert decision["mode"] == "deterministic"
    assert decision["status"] == "recommended"
    assert decision["option_id"] == RECALL_HOLD
    assert decision["citations"] == []
    assert result["decision_mode_applied"] is True
    assert "No other feasible option was available" in decision["tradeoff"]
    assert result["advisory_context"]["outcome"]["selected_option_id"] == RECALL_HOLD

    rows = _review_sections(result)["Options considered"]["rows"]
    assert rows[0]["Result"] == "Selected"
    assert rows[1]["Result"].startswith("Infeasible: RCL-001 requires the batch held")


@pytest.mark.parametrize("scenario_id", ["SCN-010", "SCN-013"])
def test_review_deterministic_never_calls_the_model(monkeypatch, scenario_id):
    def fail(*args, **kwargs):
        raise AssertionError("deterministic mode must not call the LLM")

    monkeypatch.setattr("app.decision.selector._call_review_model", fail)
    result = run_scenario(scenario_id)
    assert result["decision"]["status"] == "recommended"


def test_credit_policy_mode_confirms_the_supplied_outcome(monkeypatch):
    calls = {}

    def fake(event_context, options, infeasible, references, required_citation, subject_label):
        calls["required"] = required_citation
        calls["subject"] = subject_label
        calls["option_ids"] = [option["option_id"] for option in options]
        calls["references"] = [reference["document_id"] for reference in references]
        return (
            {"option_id": CREDIT_HOLD, "priority": "policy_requirement", "citations": ["POL-LIQ-007"]},
            "fake-model",
        )

    monkeypatch.setattr("app.decision.selector._call_review_model", fake)
    result = run_scenario("SCN-010", decision_mode="policy_grounded_llm")
    decision = result["decision"]

    assert calls["required"] == "POL-LIQ-007"
    assert calls["subject"] == "credit review outcome"
    assert calls["option_ids"] == [CREDIT_HOLD, CREDIT_PAUSE]
    assert "POL-LIQ-007" in calls["references"]
    assert decision["mode"] == "policy_grounded_llm"
    assert decision["status"] == "recommended"
    assert decision["option_id"] == CREDIT_HOLD
    assert decision["citations"] == ["POL-LIQ-007"]
    assert decision["model"] == "fake-model"
    assert result["decision_mode_applied"] is True
    assert result["advisory_context"]["outcome"]["decision_status"] == "recommended"
    summary = result["advisory_context"]["operator_summary"]
    assert "The model confirmed:" in summary and "citing POL-LIQ-007" in summary
    rationale_rows = _review_sections(result)["Decision rationale"]["rows"]
    assert {"Field": "Decided by", "Value": "The language model (fake-model)"} in rationale_rows
    assert {
        "Field": "Role of the policies",
        "Value": "The model relied on them, and the app checked every citation.",
    } in rationale_rows

    context = build_review_context(result)
    assert {"document_id": "POL-LIQ-007", "relation": "cited"}.items() <= next(
        reference for reference in context["references"] if reference["document_id"] == "POL-LIQ-007"
    ).items()


def test_recall_policy_mode_abstains_without_falling_back(monkeypatch):
    monkeypatch.setattr(
        "app.decision.selector._call_review_model",
        lambda *args, **kwargs: (
            {"option_id": None, "priority": None, "citations": [], "abstain_reason": "Recall scope is unclear."},
            "fake-model",
        ),
    )
    result = run_scenario("SCN-013", decision_mode="policy_grounded_llm")

    assert result["decision"]["status"] == "abstained"
    assert result["decision"]["option_id"] is None
    assert "Recall scope is unclear." in result["decision"]["abstain_reason"]
    assert result["advisory_context"]["outcome"]["selected_option_id"] is None
    assert result["advisory_context"]["outcome"]["decision_status"] == "abstained"
    assert result["recommendation"]["review_status"] == "needs_clarification"
    assert "did not select a review outcome" in result["advisory_context"]["operator_summary"]
    assert any(step["status"] == "blocked" for step in result["advisory_context"]["decision_steps"])
    rows = _review_sections(result)["Options considered"]["rows"]
    assert rows[0]["Result"] == "Not selected — selection stopped"


@pytest.mark.parametrize(
    ("scenario_id", "parsed", "reason"),
    [
        (
            "SCN-010",
            {"option_id": CREDIT_HOLD, "priority": "policy_requirement", "citations": ["POL-SVC-009"]},
            "did not cite the governing POL-LIQ-007",
        ),
        (
            "SCN-013",
            {"option_id": RECALL_HOLD, "priority": "policy_requirement", "citations": ["POL-RCM-007"]},
            "did not cite the governing POL-STK-007",
        ),
        (
            "SCN-010",
            {"option_id": CREDIT_PAUSE, "priority": "policy_requirement", "citations": ["POL-LIQ-007"]},
            "smaller effect",
        ),
        (
            "SCN-010",
            {"option_id": CREDIT_ACCEPT, "priority": "policy_requirement", "citations": ["POL-LIQ-007"]},
            "did not select a supplied feasible option",
        ),
    ],
)
def test_review_policy_mode_rejects_invalid_model_choices(monkeypatch, scenario_id, parsed, reason):
    monkeypatch.setattr(
        "app.decision.selector._call_review_model", lambda *args, **kwargs: (parsed, "fake-model")
    )
    result = run_scenario(scenario_id, decision_mode="policy_grounded_llm")
    assert result["decision"]["status"] == "abstained"
    assert result["decision"]["option_id"] is None
    assert reason in result["decision"]["abstain_reason"]
