from datetime import date, datetime, timedelta, timezone

from app.agents.supplier import build_supplier_options
from app.extraction import RulesExtractor
from app.extraction.base import Extraction
from app.extraction.rules import match_catalogue_name
from app.extraction.validate import validate_extraction
from app.orchestration.workflow import process_message
from app.schemas.contracts import EvidenceFact, IntentMatch, MessageSubmission

IST = timezone(timedelta(hours=5, minutes=30))


def _message(text: str, state_version: str) -> MessageSubmission:
    return MessageSubmission(
        message_id="name-test-1",
        source_type="retailer_message",
        text=text,
        observed_at=datetime(2026, 11, 1, 9, 0, tzinfo=IST),
        language="English",
        consent_status="synthetic",
        state_version=state_version,
    )


def test_supplier_trade_name_resolves_to_catalogue_id(demo_message):
    named = demo_message.model_copy(
        update={
            "message_id": "name-test-supplier",
            "text": (
                "Sri Venkateswara FMCG Supply reports a two-day delay for "
                "Cooking oil 1 L pouch; revised date is not confirmed."
            ),
        }
    )

    result = process_message(named)

    facts = {fact["field"]: fact for fact in result["event"]["extracted_facts"]}
    assert facts["supplier_id"]["value"] == "SUP-005"
    assert facts["supplier_id"]["evidence_span"] == "Sri Venkateswara FMCG Supply"
    assert result["event"]["status"] == "pending_review"
    assert (
        "Sri Venkateswara FMCG Supply (SUP-005)"
        in result["event"]["inferences"]["delayed_incoming_assumption"]
    )


def test_retailer_trade_name_resolves_to_catalogue_id(state):
    message = _message("Lakshmi Provision Store says the Biscuits delivery was late.", state.state_version)
    extraction = RulesExtractor().extract(message, state)

    violations = validate_extraction(extraction, message, state)

    assert violations == []
    retailer = extraction.fact("retailer_id")
    assert retailer.value == "RET-003"
    assert message.text[retailer.span_start : retailer.span_end] == "Lakshmi Provision Store"


def test_model_name_fact_is_converted_to_catalogue_id(state):
    message = _message(
        "Balaji Wholesale Distributors reports a two-day delay for Rice 5 kg bag.",
        state.state_version,
    )
    extraction = Extraction(
        intents=[IntentMatch(intent="supplier_delay", confidence=0.9, evidence_span="delay")],
        facts=[
            EvidenceFact(
                field="supplier_name",
                value="Balaji Wholesale Distributors",
                evidence_span="Balaji Wholesale Distributors",
            )
        ],
    )

    violations = validate_extraction(extraction, message, state)

    assert violations == []
    supplier = extraction.fact("supplier_id")
    assert supplier.value == "SUP-002"
    assert extraction.fact("supplier_name") is None


def test_unknown_supplier_name_is_not_mapped_or_planned(state):
    message = _message(
        "Gupta Traders reports a two-day delay for Cooking oil 1 L pouch.",
        state.state_version,
    )
    extraction = Extraction(
        intents=[IntentMatch(intent="supplier_delay", confidence=0.9, evidence_span="delay")],
        facts=[EvidenceFact(field="supplier_name", value="Gupta Traders", evidence_span="Gupta Traders")],
    )

    violations = validate_extraction(extraction, message, state)

    assert violations == []
    assert extraction.fact("supplier_id") is None
    assert any("catalogue" in note for note in extraction.uncertainties)


def test_written_shop_name_is_recovered_when_model_misses_it(state):
    message = _message("New Sai Kirana reports a damaged carton in the Soap delivery.", state.state_version)
    extraction = Extraction(
        intents=[IntentMatch(intent="damaged_item", confidence=0.9, evidence_span="damaged")],
        facts=[EvidenceFact(field="product", value="Soap", evidence_span="Soap")],
    )

    violations = validate_extraction(extraction, message, state)

    assert violations == []
    retailer = extraction.fact("retailer_id")
    assert retailer.value == "RET-011"
    assert retailer.evidence_span == "New Sai Kirana"
    assert message.text[retailer.span_start : retailer.span_end] == "New Sai Kirana"


def test_short_name_matching_two_shops_is_ambiguous(state):
    ambiguous = match_catalogue_name("Sai Kirana", "Sai Kirana", state.retailers, "retailer_id", "retailer_name")
    exact = match_catalogue_name(
        "New Sai Kirana", "New Sai Kirana", state.retailers, "retailer_id", "retailer_name"
    )

    assert ambiguous is None
    assert exact == "RET-011"


def test_supplier_options_carry_trade_names(state):
    options = build_supplier_options(state, "SKU-003", 46, "SUP-005", 2, date(2026, 11, 4))

    assert [option.supplier_id for option in options] == ["SUP-002", "SUP-003", "SUP-005"]
    assert options[0].supplier_name == "Balaji Wholesale Distributors"
