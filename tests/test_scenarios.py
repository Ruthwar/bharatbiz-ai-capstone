from decimal import Decimal

import pytest

from app.optimization.context import build_planning_view
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
    assert [fixture.scenario_id for fixture in fixtures] == [f"SCN-{index:03d}" for index in range(1, 10)]
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
