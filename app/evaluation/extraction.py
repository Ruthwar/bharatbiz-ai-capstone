from __future__ import annotations

import json
import math
import statistics
import time
from pathlib import Path
from typing import Callable

from app.extraction.base import Extraction, Extractor
from app.extraction.llm import LLMExtractor
from app.extraction.prompts import EXTRACTION_PROMPT_VERSION
from app.extraction.rules import RulesExtractor
from app.extraction.validate import validate_extraction
from app.orchestration.taxonomy import TAXONOMY_VERSION
from app.schemas.contracts import BusinessState, MessageSubmission
from app.state import load_business_state

PROJECT_ROOT = Path(__file__).resolve().parents[2]
HELD_OUT = PROJECT_ROOT / "data" / "eval" / "heldout_extraction.jsonl"
FIELD_ALIASES = {
    "date": ("date", "revised_date"),
    "order_reference": ("order_reference", "po_reference"),
    "quantity": ("quantity", "delayed_quantity"),
}
Progress = Callable[[dict], None]


class ExtractionEvaluationUnavailable(RuntimeError):
    pass


def _emit(progress: Progress | None, step: str, title: str, **fields) -> None:
    if progress:
        progress({"step": step, "title": title, **fields})


def load_held_out_records() -> list[dict]:
    return [json.loads(line) for line in HELD_OUT.read_text(encoding="utf-8").splitlines() if line.strip()]


def _message(record: dict, state: BusinessState) -> MessageSubmission:
    return MessageSubmission(
        message_id=record["message_id"],
        source_type="synthetic",
        text=record["text"],
        observed_at=state.as_of,
        language="unknown",
        state_version=record["state_version"],
    )


def _facts(extraction: Extraction) -> list[dict]:
    return [
        {"field": fact.field, "value": fact.value, "evidence_span": fact.evidence_span}
        for fact in extraction.facts
    ]


def _predicted_entities(extraction: Extraction, expected: dict) -> dict[str, str | None]:
    predicted = {}
    for field in expected:
        aliases = FIELD_ALIASES.get(field, (field,))
        fact = next((extraction.fact(alias) for alias in aliases if extraction.fact(alias)), None)
        predicted[field] = fact.value if fact else None
    return predicted


def _normalise(value: str | None) -> str | None:
    return " ".join(value.casefold().split()) if value is not None else None


def _score(
    extraction: Extraction,
    record: dict,
    latency_ms: float,
    violations: list[str],
    fallback: bool,
    error: str | None,
    raw_extraction: Extraction | None = None,
) -> dict:
    predicted_entities = _predicted_entities(extraction, record["entities"])
    entity_matches = {
        field: _normalise(value) == _normalise(predicted_entities[field])
        for field, value in record["entities"].items()
    }
    present_fields = [field for field, value in record["entities"].items() if value is not None]
    facts = _facts(extraction)
    return {
        "predicted_intent": extraction.primary_intent,
        "predicted_intents": [match.intent for match in extraction.intents],
        "predicted_entities": predicted_entities,
        "facts": facts,
        "intent_correct": extraction.primary_intent == record["intent"],
        "entity_matches": entity_matches,
        "entity_correct": sum(entity_matches.values()),
        "entity_total": len(entity_matches),
        "present_entity_correct": sum(entity_matches[field] for field in present_fields),
        "present_entity_total": len(present_fields),
        "record_exact": extraction.primary_intent == record["intent"] and all(entity_matches.values()),
        "validation_passed": not violations,
        "validation_violations": violations,
        "verbatim_evidence_count": sum(fact["evidence_span"] in record["text"] for fact in facts),
        "evidence_count": len(facts),
        "latency_ms": latency_ms,
        "fallback": fallback,
        "error": error,
        "raw_predicted_intent": raw_extraction.primary_intent if raw_extraction else extraction.primary_intent,
        "raw_facts": _facts(raw_extraction) if raw_extraction else facts,
    }


def _run_rules(message: MessageSubmission, state: BusinessState) -> dict:
    started = time.perf_counter()
    extraction = RulesExtractor().extract(message, state)
    violations = validate_extraction(extraction, message, state)
    latency_ms = (time.perf_counter() - started) * 1000
    return {"extraction": extraction, "latency_ms": latency_ms, "violations": violations, "fallback": False, "error": None}


def _run_llm(extractor: Extractor, message: MessageSubmission, state: BusinessState) -> dict:
    started = time.perf_counter()
    raw_extraction = None
    violations = []
    try:
        raw_extraction = extractor.extract(message, state)
        violations = validate_extraction(raw_extraction, message, state)
        if violations:
            raise ValueError("Model output failed deterministic validation")
        return {
            "extraction": raw_extraction,
            "latency_ms": (time.perf_counter() - started) * 1000,
            "violations": [],
            "fallback": False,
            "error": None,
            "raw_extraction": raw_extraction,
        }
    except Exception as exc:
        fallback = RulesExtractor().extract(message, state)
        validate_extraction(fallback, message, state)
        fallback.uncertainties.append("Model extraction was unavailable or failed validation; deterministic rules were used.")
        return {
            "extraction": fallback,
            "latency_ms": (time.perf_counter() - started) * 1000,
            "violations": violations or [type(exc).__name__],
            "fallback": True,
            "error": f"{type(exc).__name__}: {exc}",
            "raw_extraction": raw_extraction,
        }


def _latency_summary(rows: list[dict], variant: str) -> dict[str, float]:
    latencies = [row["results"][variant]["latency_ms"] for row in rows]
    return {
        "latency_ms_p50": statistics.median(latencies),
        "latency_ms_p95": sorted(latencies)[max(math.ceil(len(latencies) * 0.95) - 1, 0)],
    }


def _variant_summary(rows: list[dict], variant: str) -> dict:
    results = [row["results"][variant] for row in rows]
    entity_total = sum(result["entity_total"] for result in results)
    present_total = sum(result["present_entity_total"] for result in results)
    evidence_total = sum(result["evidence_count"] for result in results)
    return {
        "examples": len(results),
        "intent_accuracy": sum(result["intent_correct"] for result in results) / len(results),
        "entity_exact_match": sum(result["entity_correct"] for result in results) / entity_total,
        "entity_correct": sum(result["entity_correct"] for result in results),
        "entity_total": entity_total,
        "stated_entity_accuracy": (
            sum(result["present_entity_correct"] for result in results) / present_total if present_total else None
        ),
        "stated_entity_correct": sum(result["present_entity_correct"] for result in results),
        "stated_entity_total": sum(result["present_entity_total"] for result in results),
        "record_exact_match": sum(result["record_exact"] for result in results) / len(results),
        "validation_pass_rate": sum(result["validation_passed"] for result in results) / len(results),
        "verbatim_evidence_rate": (
            sum(result["verbatim_evidence_count"] for result in results) / evidence_total if evidence_total else None
        ),
        "fallback_count": sum(result["fallback"] for result in results),
        **_latency_summary(rows, variant),
    }


def run_extraction_evaluation(
    progress: Progress | None = None,
    llm_extractor: Extractor | None = None,
    records: list[dict] | None = None,
) -> dict:
    extractor = llm_extractor or LLMExtractor.from_environment()
    if extractor is None:
        raise ExtractionEvaluationUnavailable("LLM extraction is not configured; only rules evaluation is available.")
    records = records if records is not None else load_held_out_records()
    state = load_business_state(expected_version=records[0]["state_version"])
    _emit(
        progress,
        "dataset_loaded",
        f"Loaded {len(records)} frozen held-out messages",
        total=len(records),
        detail=f"Comparing deterministic rules with {getattr(extractor, 'model', 'configured LLM')}; labels are not used for tuning.",
    )
    rows = []
    for position, record in enumerate(records, start=1):
        message = _message(record, state)
        _emit(
            progress,
            "message_started",
            f"Testing {record['message_id']} ({position}/{len(records)})",
            current=position,
            total=len(records),
            detail=record["text"],
        )
        rules = _run_rules(message, state)
        llm = _run_llm(extractor, message, state)
        row = {
            "message_id": record["message_id"],
            "text": record["text"],
            "expected_intent": record["intent"],
            "expected_entities": record["entities"],
            "label_evidence_spans": record["evidence_spans"],
            "uncertainty": record["uncertainty"],
            "results": {
                "rules": _score(rules.pop("extraction"), record, **rules),
                "llm": _score(llm.pop("extraction"), record, **llm),
            },
        }
        rows.append(row)
        llm_result = row["results"]["llm"]
        _emit(
            progress,
            "message_completed",
            f"{record['message_id']}: expected {record['intent']}, LLM predicted {llm_result['predicted_intent']}",
            current=position,
            total=len(records),
            detail=(
                f"Intent {'matched' if llm_result['intent_correct'] else 'missed'}; "
                f"{llm_result['entity_correct']}/{llm_result['entity_total']} entity slots matched; "
                f"{'rules fallback used' if llm_result['fallback'] else 'validated LLM output used'}."
            ),
            outcome="passed" if llm_result["record_exact"] else "failed",
            row=row,
        )
    summary = {
        "examples": len(records),
        "dataset": "data/eval/heldout_extraction.jsonl",
        "split": "held_out",
        "source_type": "synthetic",
        "state_version": state.state_version,
        "prompt_version": EXTRACTION_PROMPT_VERSION,
        "taxonomy_version": TAXONOMY_VERSION,
        "llm_model": getattr(extractor, "model", "configured LLM"),
        "variants": {variant: _variant_summary(rows, variant) for variant in ("rules", "llm")},
    }
    _emit(progress, "metrics_completed", "Extraction metrics calculated", detail="Computed intent, entity, exact-record, evidence, validation, fallback and latency metrics.", outcome="passed")
    return {"summary": summary, "rows": rows}
