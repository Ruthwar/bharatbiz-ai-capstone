import re

import pytest
from fastapi.testclient import TestClient

from app.extraction.base import Extraction
from app.extraction.rules import product_clarification_options, resolve_product
from app.extraction.validate import validate_extraction
from app.main import app
from app.orchestration import workflow
from app.orchestration.acks import ACK_TEXTS
from app.orchestration.router import registered_intents
from app.schemas.contracts import EvidenceFact, IntentMatch, MessageSubmission
from app.state import load_business_state
from app.store.ledger import ledger

client = TestClient(app)
STATE_VERSION = "synthetic-v3-live-20261123"
SCN003_TEXT = "Supplier SUP-005 reports a two-day delay for Cooking oil 1 L pouch; revised date is not confirmed."


@pytest.fixture(autouse=True)
def clear_ledger():
    ledger.reset()
    yield
    ledger.reset()


def post(text: str, **overrides) -> dict:
    payload = {
        "text": text,
        "conversation_id": "c1",
        "sender_type": "supplier",
        "sender_id": "SUP-005",
        "state_version": STATE_VERSION,
        **overrides,
    }
    response = client.post("/api/v1/inbound", json=payload)
    assert response.status_code == 200, response.text
    return response.json()


def test_acknowledgements_never_assert_anything():
    for kind, translations in ACK_TEXTS.items():
        for language, text in translations.items():
            assert not re.search(r"\d", text), (kind, language)
            assert "₹" not in text, (kind, language)
            for promise in ("tomorrow", "will arrive", "delivered by", "kal", "deliver"):
                assert promise not in text.lower(), (kind, language, promise)


def test_supplier_delay_is_acknowledged_and_planned():
    result = post(SCN003_TEXT, sender_type="supplier", sender_id="SUP-005")

    assert result["ack"]["kind"] == "receipt"
    assert result["completion_ack"]["kind"] == "complete"
    assert result["routed_action"] == "supplier_delay_planning"
    assert result["event"]["event_type"] == "supplier_delay"
    assert result["recommendation"]["review_status"] == "pending_review"
    assert len(ledger.pending_reviews()) == 1


def test_demand_spike_uses_percentage_stated_in_message():
    result = post(
        "Demand spike: Biscuits small carton ke open orders rise by 60 percent hone ki expectation hai.",
        sender_type="sales_rep",
        sender_id=None,
        language="Hinglish",
        conversation_id="c-demand-uplift",
    )

    assert result["routed_action"] == "demand_spike_planning"
    assert result["question"] is None
    assert result["event"]["inferences"]["catalogue_sku_id"] == "SKU-006"
    assert result["result"]["selected_plan"] is not None
    assert result["result"]["verification"]["valid"] is True


def test_selected_supplier_account_supplies_id_omitted_from_message():
    result = post(
        "Cooking oil 1 L pouch ki delivery mein two-day delay hai; revised date confirmed nahi hai.",
        sender_type="supplier",
        sender_id="SUP-005",
        language="Hinglish",
        conversation_id="c-sender-identity",
    )

    assert result["routed_action"] == "supplier_delay_planning"
    assert result["question"] is None
    assert result["recommendation"]["review_status"] == "pending_review"
    assert result["result"]["selected_plan"] is not None
    assert result["result"]["verification"]["valid"] is True
    assert ledger.pending_reviews()[0]["why"] is not None


def test_missing_supplier_account_and_text_id_asks_for_supplier_reference():
    result = post(
        "Cooking oil 1 L pouch has a two-day delay.",
        sender_type="supplier",
        sender_id=None,
        conversation_id="c-missing-supplier",
    )

    assert result["routed_action"] == "slot_question"
    assert result["question"] == "Which supplier reference is this about?"
    assert result["completion_ack"] is None


def test_review_item_explains_the_trade_off():
    post(SCN003_TEXT, sender_type="supplier", sender_id="SUP-005")
    why = ledger.pending_reviews()[0]["why"]

    assert why["requested_units"] == 102
    assert why["usable_units"] == 56
    assert why["required_units"] == 46
    assert why["verification_valid"] is True

    alternatives = {row["label"]: row for row in why["alternatives"]}
    assert alternatives["Stock only"]["unmet_units"] == 46
    selected = alternatives["Balaji Wholesale Distributors (SUP-002)"]
    assert selected["selected"] is True
    assert selected["late_units"] == 28
    assert alternatives["Krishna Rice Mills (SUP-003)"]["late_units"] == 28
    assert selected["arrival_date"] < alternatives["Krishna Rice Mills (SUP-003)"]["arrival_date"]


def test_triage_item_has_no_plan_explanation():
    post("Please look into it when you get time.", sender_type="retailer", sender_id="RET-004")

    assert ledger.pending_reviews()[0]["why"] is None


def test_missing_slot_triggers_one_question_then_completes():
    first = post(
        "SUP-005 reports a two-day delay; revised date is not confirmed.",
        sender_type="supplier",
        sender_id="SUP-005",
    )

    assert first["routed_action"] == "slot_question"
    assert first["question"]
    assert first["completion_ack"] is None

    second = post(
        "Cooking oil 1 L pouch",
        sender_type="supplier",
        sender_id="SUP-005",
        conversation_id="c1",
    )

    assert second["routed_action"] == "supplier_delay_planning"
    assert second["completion_ack"]["kind"] == "complete"
    assert second["event"]["inferences"]["catalogue_sku_id"] == "SKU-003"
    assert second["event"]["source_message_ids"]


def test_product_pack_variation_completes_clarification():
    post(
        "SUP-005 reports a two-day delay; revised date is not confirmed.",
        sender_type="supplier",
        sender_id="SUP-005",
        conversation_id="c-product-variation",
    )

    result = post(
        "Cooking oil 1 L product is effected",
        sender_type="supplier",
        sender_id="SUP-005",
        conversation_id="c-product-variation",
    )

    assert result["routed_action"] == "supplier_delay_planning"
    assert result["question"] is None
    assert result["event"]["inferences"]["catalogue_sku_id"] == "SKU-003"


def test_ambiguous_product_question_lists_filtered_options_and_accepts_selection():
    first = post(
        "SUP-005 reports a two-day delay for Cooking oil.",
        sender_type="supplier",
        sender_id="SUP-005",
        conversation_id="c-product-options",
    )

    assert first["routed_action"] == "slot_question"
    assert "Reply with one option:" in first["question"]
    assert "Cooking oil 1 L pouch" in first["question"]
    assert "Cooking oil 5 L tin" in first["question"]
    assert "Rice 10 kg bag" not in first["question"]

    second = post(
        "Cooking oil 5 L tin",
        sender_type="supplier",
        sender_id="SUP-005",
        conversation_id="c-product-options",
    )

    assert second["routed_action"] == "supplier_delay_planning"
    assert second["question"] is None
    assert second["event"]["inferences"]["catalogue_sku_id"] == "SKU-004"


def test_two_missing_slots_are_asked_in_separate_turns():
    first = post(
        "SUP-005 reports that delivery is late.",
        sender_type="supplier",
        sender_id="SUP-005",
        conversation_id="c-two",
    )

    assert first["routed_action"] == "slot_question"
    assert first["question"] == "Which product and pack is affected?"

    second = post(
        "Cooking oil 1 L pouch",
        sender_type="supplier",
        sender_id="SUP-005",
        conversation_id="c-two",
    )

    assert second["routed_action"] == "slot_question"
    assert second["question"] == "How many days is the delay?"

    third = post(
        "2-day delay",
        sender_type="supplier",
        sender_id="SUP-005",
        conversation_id="c-two",
    )

    assert third["routed_action"] == "supplier_delay_planning"
    assert third["recommendation"]["review_status"] == "pending_review"


@pytest.mark.parametrize(("prior_rounds", "expected_action"), [(3, "slot_question"), (4, "human_triage")])
def test_four_clarification_rounds_are_allowed_before_human_triage(prior_rounds, expected_action):
    ledger.open_intake("c-cap", "previous-message", "SUP-005 reports that delivery is late.", prior_rounds)

    result = post(
        "SUP-005 reports that delivery is late.",
        sender_type="supplier",
        sender_id="SUP-005",
        conversation_id="c-cap",
    )

    assert result["rounds"] == prior_rounds
    assert result["routed_action"] == expected_action
    assert (result["question"] is not None) is (prior_rounds < 4)


def test_retailer_cannot_report_a_supplier_delay():
    result = post(SCN003_TEXT, sender_type="retailer", sender_id="RET-004")

    assert result["routed_action"] == "human_triage"
    assert result["recommendation"] is None
    assert any("supplier account" in note for note in result["event"]["uncertainties"])
    item = ledger.pending_reviews()[0]
    assert item["why"] is None


def test_reported_supplier_must_match_the_sending_account():
    result = post(SCN003_TEXT, sender_type="supplier", sender_id="SUP-002")

    assert result["routed_action"] == "human_triage"
    assert any("does not match" in note for note in result["event"]["uncertainties"])


def test_unknown_message_keeps_facts_and_goes_to_triage():
    result = post("Please look into it when you get time.", sender_type="retailer", sender_id="RET-004")

    assert result["event"]["event_type"] == "unclassified"
    assert result["routed_action"] == "human_triage"
    assert result["completion_ack"] is None
    assert len(ledger.pending_reviews()) == 1


def test_duplicate_message_is_acknowledged_once():
    first = post(SCN003_TEXT, sender_type="supplier", sender_id="SUP-005", message_id="wa-1")
    second = post(SCN003_TEXT, sender_type="supplier", sender_id="SUP-005", message_id="wa-1")

    assert first["duplicate"] is False
    assert second["duplicate"] is True
    assert second["ack"]["status"] == "duplicate"
    assert len(ledger.pending_reviews()) == 1


def test_state_mismatch_still_acknowledges_and_triages():
    result = post(SCN003_TEXT, sender_type="supplier", sender_id="SUP-005", state_version="sim-v1")

    assert result["ack"]["kind"] == "receipt"
    assert result["ack"]["status"] == "triaged"
    assert result["processing_error"] == "StateVersionMismatch"
    assert result["routed_action"] == "human_triage"


def test_human_review_decision_clears_the_queue():
    post(SCN003_TEXT, sender_type="supplier", sender_id="SUP-005")
    item = ledger.pending_reviews()[0]

    response = client.post(f"/api/v1/review/{item['event_id']}", json={"decision": "approve", "reviewer": "owner"})

    assert response.status_code == 200
    assert response.json()["review_status"] == "approved"
    assert ledger.pending_reviews() == []


def test_only_implemented_intents_have_handlers():
    assert registered_intents() == (
        "baseline",
        "batch_recall",
        "combined_disruption",
        "competitor_observation",
        "credit_check",
        "damaged_item",
        "delivery_complaint",
        "delivery_discrepancy",
        "demand_spike",
        "dispatch_planning",
        "limited_cash",
        "missing_item",
        "product_request",
        "scheme_claim",
        "short_dated_stock",
        "stock_discrepancy",
        "supplier_delay",
    )


def test_evidence_that_is_not_verbatim_is_dropped():
    state = load_business_state(expected_version=STATE_VERSION)
    message = MessageSubmission(
        message_id="m-1",
        source_type="supplier_update",
        text="SUP-005 reports a two-day delay.",
        observed_at="2026-11-01T09:00:00+05:30",
        state_version=STATE_VERSION,
    )
    extraction = Extraction(
        intents=[IntentMatch(intent="supplier_delay", confidence=0.9)],
        facts=[
            EvidenceFact(field="supplier_id", value="SUP-005", evidence_span="SUP-005"),
            EvidenceFact(field="delay_days", value="2", evidence_span="two-day"),
            EvidenceFact(field="po_reference", value="PO-999", evidence_span="PO-999"),
        ],
    )

    violations = validate_extraction(extraction, message, state)
    fields = {fact.field for fact in extraction.facts}

    assert violations == []
    assert "po_reference" not in fields
    assert any("not found verbatim" in item for item in extraction.uncertainties)
    assert extraction.facts[1].span_start == message.text.index("two-day")


def test_validation_recovers_uplift_omitted_by_model():
    text = "Demand spike: Biscuits small carton ke open orders rise by 60 percent hone ki expectation hai."
    message = MessageSubmission(
        message_id="m-demand-uplift",
        source_type="sales_visit",
        text=text,
        observed_at="2026-11-01T09:00:00+05:30",
        state_version=STATE_VERSION,
    )
    extraction = Extraction(
        intents=[IntentMatch(intent="demand_spike", confidence=0.9)],
        facts=[EvidenceFact(field="product", value="Biscuits small carton", evidence_span="Biscuits small carton")],
        mode="llm",
    )

    violations = validate_extraction(extraction, message, load_business_state(expected_version=STATE_VERSION))
    uplift = extraction.fact("demand_uplift_percent")

    assert violations == []
    assert uplift is not None
    assert uplift.value == "60"
    assert uplift.evidence_span == "60"
    assert text[uplift.span_start:uplift.span_end] == "60"
    assert extraction.inferences["catalogue_sku_id"] == "SKU-006"


def test_ambiguous_product_never_gets_a_sku():
    state = load_business_state(expected_version=STATE_VERSION)

    assert resolve_product(state, "Rice") is None
    assert resolve_product(state, "Cooking oil") is None
    assert resolve_product(state, "Cooking oil 1 L pouch")["sku_id"] == "SKU-003"


@pytest.mark.parametrize(
    ("text", "expected_sku"),
    [
        ("Cooking oil 1 L product is effected", "SKU-003"),
        ("Cooking oil 1L", "SKU-003"),
        ("1 litre Cooking oil", "SKU-003"),
        ("Rice 10 kg", "SKU-002"),
    ],
)
def test_unique_product_and_pack_size_variations_resolve(text, expected_sku):
    state = load_business_state(expected_version=STATE_VERSION)

    assert resolve_product(state, text)["sku_id"] == expected_sku


@pytest.mark.parametrize("text", ["pouch", "Cooking oil 3 L", "Rice 10 kg and Rice 5 kg"])
def test_incomplete_or_ambiguous_pack_variations_do_not_resolve(text):
    state = load_business_state(expected_version=STATE_VERSION)

    assert resolve_product(state, text) is None


def test_product_options_use_category_size_and_supplier_availability():
    state = load_business_state(expected_version=STATE_VERSION)

    assert product_clarification_options(state, "Cooking oil", "SUP-005") == [
        "Cooking oil 1 L pouch",
        "Cooking oil 5 L tin",
    ]
    assert product_clarification_options(state, "Cooking oil", "SUP-004") == [
        "Cooking oil 5 L tin"
    ]
    assert product_clarification_options(state, "Cooking oil 1 L", "SUP-005") == [
        "Cooking oil 1 L pouch"
    ]
    assert product_clarification_options(state, "Cooking oil 3 L", "SUP-005") == []
    assert product_clarification_options(state, "delivery is late", "SUP-005") == []


def test_the_decision_pipeline_is_graph_backed():
    from app.orchestration.inbound import inbound_graph
    from app.orchestration.workflow import plan_graph

    assert {
        "load_state",
        "extract",
        "build_event",
        "authorize",
        "plan",
        "triage",
        "review_gate",
        "finalize",
    } <= set(plan_graph.get_graph().nodes)
    assert {"dedup", "intake", "plan", "slot_gate", "ask_follow_up", "close_and_queue"} <= set(
        inbound_graph.get_graph().nodes
    )


def test_failed_verification_never_reaches_human_review(monkeypatch):
    class InvalidVerification:
        valid = False
        violations = ["stub: allocation exceeds available stock"]

        def model_dump(self, mode: str = "json") -> dict:
            return {"valid": self.valid, "violations": list(self.violations)}

    monkeypatch.setattr(workflow, "verify_plan", lambda *args, **kwargs: InvalidVerification())
    message = MessageSubmission(
        message_id="m-gate",
        source_type="supplier_update",
        text=SCN003_TEXT,
        observed_at="2026-11-01T09:00:00+05:30",
        state_version=STATE_VERSION,
    )

    result = workflow.process_message(message)

    assert result["recommendation"]["review_status"] == "needs_clarification"
    assert "verification_failed" in result["trace"]
    assert "stub: allocation exceeds available stock" in result["recommendation"]["warnings"]
