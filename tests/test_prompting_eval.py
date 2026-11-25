from app.evaluation.extraction import load_held_out_records
from app.evaluation.prompting import (
    FEW_SHOT_EXAMPLES,
    STRATEGIES,
    StrategySpec,
    estimate_cost,
    run_prompting_evaluation,
)
from app.extraction.base import Extraction
from app.schemas.contracts import EvidenceFact, IntentMatch

RECORD = {
    "message_id": "TEST-PROMPT-1",
    "split": "held_out",
    "source_type": "synthetic",
    "state_version": "synthetic-v3-live-20261123",
    "text": "SUP-999 reports a two-day delay for Cooking oil 1 L pouch.",
    "intent": "supplier_delay",
    "entities": {
        "product": "Cooking oil 1 L pouch",
        "retailer_id": None,
        "order_reference": None,
        "quantity": None,
        "date": None,
    },
    "evidence_spans": ["two-day delay"],
    "uncertainty": "Revised date is not stated.",
}


def _valid() -> Extraction:
    return Extraction(
        intents=[IntentMatch(intent="supplier_delay", confidence=0.9, evidence_span="two-day delay")],
        facts=[
            EvidenceFact(
                field="product",
                value="Cooking oil 1 L pouch",
                evidence_span="Cooking oil 1 L pouch",
            )
        ],
        mode="llm",
    )


def _invalid() -> Extraction:
    return Extraction(
        intents=[IntentMatch(intent="supplier_delay", confidence=0.9, evidence_span="two-day delay")],
        facts=[EvidenceFact(field="supplier_id", value="SUP-999", evidence_span="SUP-999")],
        mode="llm",
    )


class StubExtractor:
    model = "stub-model"

    def __init__(self, spec: StrategySpec) -> None:
        self.spec = spec
        self.calls = 0
        self.last_usage = {"prompt_tokens": 100, "completion_tokens": 20}

    def extract(self, message, state):
        self.calls += 1
        if self.spec.name == "zero_shot":
            return _invalid()
        if self.spec.repair and self.calls == 1:
            return _invalid()
        return _valid()


def test_repair_and_prompt_variants_are_measured_with_tokens():
    result = run_prompting_evaluation(
        factory=StubExtractor,
        records=[RECORD],
        strategies=(
            StrategySpec("zero_shot", ""),
            StrategySpec("zero_shot_repair", "", repair=True),
            StrategySpec("few_shot", "", few_shot=True),
        ),
    )
    summary = result["summary"]

    assert summary["llm_available"] is True
    assert summary["model"] == "stub-model"
    zero = summary["strategies"]["zero_shot"]
    repair = summary["strategies"]["zero_shot_repair"]
    few = summary["strategies"]["few_shot"]

    assert zero["fallback_count"] == 1
    assert zero["error_count"] == 1
    assert zero["validation_pass_rate"] == 0.0
    assert zero["record_exact_match"] == 1.0  # the rules fallback still recovers this simple record
    assert zero["failure_labels"]["tool_call_error"] == 1
    assert zero["estimated_cost"] is None
    assert repair["repair_attempts"] == 1
    assert repair["repair_successes"] == 1
    assert repair["fallback_count"] == 0
    assert repair["record_exact_match"] == 1.0
    assert repair["model_calls"] == 2
    assert repair["total_tokens"] == 240
    assert few["record_exact_match"] == 1.0
    assert few["total_tokens"] == 120


def test_cost_requires_an_explicit_rate(monkeypatch):
    monkeypatch.delenv("BHARATBIZ_TRACE_COST_PER_1K_TOKENS", raising=False)
    assert estimate_cost(1000, 200) is None
    monkeypatch.setenv("BHARATBIZ_TRACE_COST_PER_1K_TOKENS", "2")
    assert estimate_cost(1000, 200) == 2.4


def test_default_strategies_carry_their_prompt_variants():
    variants = {spec.name: (spec.few_shot, spec.repair) for spec in STRATEGIES}

    assert variants == {
        "rules": (False, False),
        "zero_shot": (False, False),
        "few_shot": (True, False),
        "zero_shot_repair": (False, True),
        "few_shot_repair": (True, True),
    }


def test_few_shot_examples_do_not_use_held_out_messages():
    held_out = {record["text"] for record in load_held_out_records()}

    assert FEW_SHOT_EXAMPLES
    assert all(text not in held_out for text, _ in FEW_SHOT_EXAMPLES)


def test_few_shot_examples_follow_the_extraction_contract():
    facts = [fact for _, payload in FEW_SHOT_EXAMPLES for fact in payload["facts"]]
    by_field = {fact["field"]: fact for fact in facts}

    assert "supplier_name" in by_field and "retailer_name" in by_field
    assert "supplier_id" not in by_field and "retailer_id" not in by_field
    assert by_field["quantity"]["value"].isdigit()
    assert by_field["delay_days"]["value"].isdigit()
