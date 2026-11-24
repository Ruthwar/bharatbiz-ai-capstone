from datetime import date

import pytest

from app.decision import DecisionModeError
from app.decision import selector
from app.decision.selector import (
    DECISION_PROMPT_VERSION,
    _applicable_policy_ids,
    _fact_payload,
    policy_context,
    recommend_plan,
)
from app.rag.retrieval import party_allows
from app.scenarios.service import run_scenario
from app.schemas.contracts import CandidatePlan, EvidenceFact

AS_OF = date(2026, 11, 23)
SUPPLIER_ID = "SUP-005"
DELAY_CITATIONS = ["POL-DLY-001", "POL-SVC-009"]


@pytest.fixture
def bundle(demo_message):
    result = run_scenario("SCN-003")
    return {
        "event": result["event"],
        "candidates": [CandidatePlan.model_validate(row) for row in result["candidate_plans"]],
        "message": demo_message,
    }


def _candidate(bundle, candidate_id: str) -> CandidatePlan:
    return next(plan for plan in bundle["candidates"] if plan.candidate_id == candidate_id)


def _recommend(monkeypatch, parsed: dict, bundle, candidates=None):
    calls: dict = {}

    def fake_call_model(event_context, candidate_list, references):
        calls["event_context"] = event_context
        calls["candidates"] = candidate_list
        calls["references"] = references
        return dict(parsed), "stub-model"

    monkeypatch.setattr(selector, "_call_model", fake_call_model)
    selected, record = recommend_plan(
        "policy_grounded_llm",
        bundle["candidates"] if candidates is None else candidates,
        bundle["message"],
        bundle["event"],
        SUPPLIER_ID,
        AS_OF,
    )
    return selected, record, calls


def test_deterministic_mode_keeps_fixed_ranking_and_no_citations(bundle):
    selected, record = recommend_plan(
        "deterministic",
        bundle["candidates"],
        bundle["message"],
        bundle["event"],
        SUPPLIER_ID,
        AS_OF,
    )
    assert selected.candidate_id == "supplier-SUP-002"
    assert record["status"] == "recommended"
    assert record["mode"] == "deterministic"
    assert record["citations"] == []
    assert record["retrieved_policies"] == []


def test_unknown_decision_mode_is_rejected(bundle):
    with pytest.raises(DecisionModeError, match="Unknown decision mode"):
        recommend_plan(
            "model_guess",
            bundle["candidates"],
            bundle["message"],
            bundle["event"],
            SUPPLIER_ID,
            AS_OF,
        )


def test_no_candidates_abstains_without_calling_the_model(monkeypatch, bundle):
    def fail(*args, **kwargs):
        raise AssertionError("the model must not be called without verified candidates")

    monkeypatch.setattr(selector, "_call_model", fail)
    selected, record = recommend_plan(
        "policy_grounded_llm",
        [],
        bundle["message"],
        bundle["event"],
        SUPPLIER_ID,
        AS_OF,
    )
    assert selected is None
    assert record["status"] == "abstained"
    assert record["abstain_reason"] == "No verified eligible plan is available."


def test_event_facts_are_serialized_whether_dicts_or_models(monkeypatch, bundle):
    parsed = {
        "candidate_id": "supplier-SUP-002",
        "priority": "service",
        "citations": DELAY_CITATIONS,
        "abstain_reason": None,
    }
    selected, record, calls = _recommend(monkeypatch, parsed, bundle)
    assert selected is not None and record["status"] == "recommended"
    facts = calls["event_context"]["verified_facts"]
    assert facts and all(isinstance(fact, dict) for fact in facts)
    assert {"product", "delay_days", "supplier_id"} <= {fact["field"] for fact in facts}
    assert all("evidence_span" in fact for fact in facts)

    model_fact = EvidenceFact(
        field="supplier_id",
        value="SUP-005",
        evidence_span="SUP-005",
        confidence="reported",
    )
    assert _fact_payload(model_fact) == {
        "field": "supplier_id",
        "value": "SUP-005",
        "evidence_span": "SUP-005",
        "span_start": None,
        "span_end": None,
        "confidence": "reported",
    }


def test_model_abstention_is_preserved_without_deterministic_fallback(monkeypatch, bundle):
    parsed = {
        "candidate_id": None,
        "priority": None,
        "citations": ["POL-DEC-008"],
        "abstain_reason": "The retrieved passages conflict on late-unit tolerance.",
    }
    selected, record, _ = _recommend(monkeypatch, parsed, bundle)
    assert selected is None
    assert record["status"] == "abstained"
    assert record["abstain_reason"] == "The retrieved passages conflict on late-unit tolerance."
    assert record["citations"] == ["POL-DEC-008"]
    assert record["model"] == "stub-model"
    assert "not run as a fallback" in record["rationale"]


def test_invented_candidate_is_rejected(monkeypatch, bundle):
    parsed = {
        "candidate_id": "supplier-SUP-999",
        "priority": "service",
        "citations": DELAY_CITATIONS,
        "abstain_reason": None,
    }
    selected, record, _ = _recommend(monkeypatch, parsed, bundle)
    assert selected is None
    assert record["status"] == "abstained"
    assert "did not select a supplied verified candidate" in record["abstain_reason"]


def test_unsupported_citation_is_rejected(monkeypatch, bundle):
    parsed = {
        "candidate_id": "supplier-SUP-002",
        "priority": "service",
        "citations": ["POL-NOT-IN-CORPUS"],
        "abstain_reason": None,
    }
    selected, record, _ = _recommend(monkeypatch, parsed, bundle)
    assert selected is None
    assert "unsupported policy citations" in record["abstain_reason"]


def test_service_priority_requires_the_service_policy_citation(monkeypatch, bundle):
    parsed = {
        "candidate_id": "supplier-SUP-002",
        "priority": "service",
        "citations": ["POL-DLY-001"],
        "abstain_reason": None,
    }
    selected, record, _ = _recommend(monkeypatch, parsed, bundle)
    assert selected is None
    assert "did not cite POL-SVC-009" in record["abstain_reason"]


def test_governing_event_policy_citation_is_required(monkeypatch, bundle):
    parsed = {
        "candidate_id": "supplier-SUP-002",
        "priority": "service",
        "citations": ["POL-SVC-009"],
        "abstain_reason": None,
    }
    selected, record, _ = _recommend(monkeypatch, parsed, bundle)
    assert selected is None
    assert "did not cite the governing POL-DLY-001 passage" in record["abstain_reason"]


def test_service_priority_rejects_a_worse_fulfilment_outcome(monkeypatch, bundle):
    parsed = {
        "candidate_id": "stock-only",
        "priority": "service",
        "citations": DELAY_CITATIONS,
        "abstain_reason": None,
    }
    selected, record, _ = _recommend(monkeypatch, parsed, bundle)
    assert selected is None
    assert "better verified fulfilment outcome was available" in record["abstain_reason"]


def test_service_priority_rejects_an_equally_good_but_later_plan(monkeypatch, bundle):
    parsed = {
        "candidate_id": "supplier-SUP-005",
        "priority": "service",
        "citations": DELAY_CITATIONS,
        "abstain_reason": None,
    }
    selected, record, _ = _recommend(monkeypatch, parsed, bundle)
    assert selected is None
    assert "meets the same fulfilment and arrives earlier" in record["abstain_reason"]


def test_a_dominated_plan_is_rejected_under_any_priority(monkeypatch, bundle):
    # SUP-003 and SUP-005 arrive on the same date with the same fulfilment, but SUP-005 is cheaper.
    parsed = {
        "candidate_id": "supplier-SUP-003",
        "priority": "service_and_cost",
        "citations": ["POL-DLY-001", "POL-SVC-009", "POL-CST-010"],
        "abstain_reason": None,
    }
    selected, record, _ = _recommend(monkeypatch, parsed, bundle)
    assert selected is None
    assert "matches or beats on fulfilment, arrival and cost" in record["abstain_reason"]


def test_cost_priority_rejects_a_pricier_plan(monkeypatch, bundle):
    parsed = {
        "candidate_id": "supplier-SUP-002",
        "priority": "cost",
        "citations": ["POL-DLY-001", "POL-CST-010"],
        "abstain_reason": None,
    }
    selected, record, _ = _recommend(monkeypatch, parsed, bundle)
    assert selected is None
    assert "cheaper eligible plan was available" in record["abstain_reason"]


def test_cost_priority_requires_the_cost_policy_citation(monkeypatch, bundle):
    parsed = {
        "candidate_id": "supplier-SUP-005",
        "priority": "cost",
        "citations": ["POL-DLY-001"],
        "abstain_reason": None,
    }
    selected, record, _ = _recommend(monkeypatch, parsed, bundle)
    assert selected is None
    assert "did not cite POL-CST-010" in record["abstain_reason"]


def test_valid_selection_builds_fact_grounded_rationale_and_tradeoff(monkeypatch, bundle):
    parsed = {
        "candidate_id": "supplier-SUP-005",
        "priority": "cost",
        "citations": ["POL-DLY-001", "POL-CST-010"],
        "abstain_reason": None,
    }
    selected, record, calls = _recommend(monkeypatch, parsed, bundle)
    assert selected.candidate_id == "supplier-SUP-005"
    assert record["status"] == "recommended"
    assert record["priority"] == "cost"
    assert record["citations"] == ["POL-DLY-001", "POL-CST-010"]
    assert record["prompt_version"] == DECISION_PROMPT_VERSION
    assert record["model"] == "stub-model"
    assert "Priority: cost" in record["rationale"]
    assert "102/102 units fulfilled, 28 late, 0 unfilled" in record["rationale"]
    assert "total cost ₹4342.86" in record["rationale"]
    assert "headroom ₹195657.14" in record["rationale"]
    assert "not supplier commitments" in record["rationale"]
    assert "Balaji Wholesale Distributors (SUP-002)" in record["tradeoff"]
    assert "purchase cost ₹533.60 more" in record["tradeoff"]
    assert "estimated arrival 2026-11-26 versus 2026-11-25" in record["tradeoff"]
    allowed = {reference["document_id"] for reference in calls["references"]}
    assert set(record["citations"]) <= allowed
    assert allowed == {
        "POL-DEC-008",
        "POL-SVC-009",
        "POL-DLY-001",
        "POL-CST-010",
        "POL-CSH-002",
        "POL-LIQ-007",
    }


def test_policy_mode_abstains_when_the_provider_is_not_configured(bundle):
    selected, record = recommend_plan(
        "policy_grounded_llm",
        bundle["candidates"],
        bundle["message"],
        bundle["event"],
        SUPPLIER_ID,
        AS_OF,
    )
    assert selected is None
    assert record["status"] == "abstained"
    assert "not configured" in record["abstain_reason"]
    assert "not run as a fallback" in record["rationale"]


def test_baseline_decisions_use_only_baseline_policies_in_force():
    context = policy_context("baseline", None, AS_OF)
    assert {row["document_id"] for row in context["passages"]} == {
        "POL-DEC-008",
        "POL-SVC-009",
        "POL-CST-010",
        "POL-CSH-002",
        "POL-LIQ-007",
    }
    assert context["not_yet_effective"] == []


def test_applicability_respects_effective_dates_supplier_scope_and_status():
    before = _applicable_policy_ids("supplier_delay", "SUP-001", date(2026, 11, 1))
    after = _applicable_policy_ids("supplier_delay", "SUP-001", date(2026, 11, 21))
    assert "POL-LIQ-007" not in before
    assert "POL-LIQ-007" in after
    assert {"POL-DEC-008", "POL-SVC-009", "POL-DLY-001", "POL-CST-010", "POL-CSH-002"} <= set(before)

    assert party_allows("all", "SUP-001")
    assert party_allows("RET-all", "SUP-001")
    assert party_allows("SUP-001, SUP-002", "SUP-002")
    assert not party_allows("SUP-002", "SUP-001")
    assert party_allows("SUP-002", None)


def test_end_to_end_policy_mode_wires_selection_trace_and_review(monkeypatch):
    def fake_call_model(event_context, candidates, references):
        assert {plan.candidate_id for plan in candidates} >= {"supplier-SUP-002", "supplier-SUP-005"}
        return {
            "candidate_id": "supplier-SUP-005",
            "priority": "cost",
            "citations": ["POL-DLY-001", "POL-CST-010"],
            "abstain_reason": None,
        }, "stub-model"

    monkeypatch.setattr(selector, "_call_model", fake_call_model)
    result = run_scenario("SCN-003", decision_mode="policy_grounded_llm")

    assert result["review_kind"] == "operational_plan"
    assert result["decision_mode"] == "policy_grounded_llm"
    assert result["decision"]["status"] == "recommended"
    assert result["decision"]["mode"] == "policy_grounded_llm"
    assert result["decision"]["citations"] == ["POL-DLY-001", "POL-CST-010"]
    assert result["selected_plan"]["candidate_id"] == "supplier-SUP-005"
    assert result["verification"]["valid"] is True
    assert result["recommendation"]["review_status"] == "pending_review"
    assert result["trace"][-2:] == ["decision_recommended", "pending_human_review"]
    assert "abstain_reason" not in result["decision"]
