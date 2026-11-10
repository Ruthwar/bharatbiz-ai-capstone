import re

import pytest
from fastapi.testclient import TestClient

from app.extraction.base import Extraction
from app.extraction.rules import resolve_product
from app.extraction.validate import validate_extraction
from app.main import app
from app.orchestration.acks import ACK_TEXTS
from app.orchestration.router import registered_intents
from app.schemas.contracts import EvidenceFact, IntentMatch, MessageSubmission
from app.state import load_business_state
from app.store.ledger import ledger

client = TestClient(app)
STATE_VERSION = "synthetic-v2-seed-20261105"
SCN003_TEXT = "Supplier SUP-005 reports a two-day delay for Cooking oil 1 L pouch; revised date is not confirmed."


@pytest.fixture(autouse=True)
def clear_ledger():
    ledger.reset()
    yield
    ledger.reset()


def post(text: str, **overrides) -> dict:
    payload = {"text": text, "conversation_id": "c1", "state_version": STATE_VERSION, **overrides}
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
    assert registered_intents() == ("supplier_delay",)


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


def test_ambiguous_product_never_gets_a_sku():
    state = load_business_state(expected_version=STATE_VERSION)

    assert resolve_product(state, "Rice") is None
    assert resolve_product(state, "Cooking oil 1 L pouch")["sku_id"] == "SKU-003"
