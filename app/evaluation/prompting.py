"""Prompting-strategy comparison on the frozen held-out extraction set.

Every strategy is scored with the same dashboard graders. Token counts come from the gateway's
reported usage; cost is left unpriced unless an explicit illustrative rate is configured. The
held-out labels are never placed in a prompt: few-shot examples come from the scenario fixtures.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import statistics
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from app.evaluation.extraction import (
    HELD_OUT,
    ExtractionEvaluationUnavailable,
    load_held_out_records,
    score_extraction,
)
from app.extraction.base import Extractor
from app.extraction.llm import LLMExtractor
from app.extraction.prompts import EXTRACTION_PROMPT_VERSION, SYSTEM_PROMPT
from app.extraction.rules import RulesExtractor
from app.extraction.validate import validate_extraction
from app.schemas.contracts import BusinessState, MessageSubmission
from app.state import load_business_state

COST_RATE_ENV = "BHARATBIZ_TRACE_COST_PER_1K_TOKENS"

FEW_SHOT_EXAMPLES: tuple[tuple[str, dict], ...] = (
    (
        "Sri Venkateswara FMCG Supply reports a two-day delay for Cooking oil 1 L pouch; "
        "revised date is not confirmed.",
        {
            "intents": [{"intent": "supplier_delay", "confidence": 0.9, "evidence": "reports a two-day delay"}],
            "facts": [
                {"field": "supplier_name", "value": "Sri Venkateswara FMCG Supply", "evidence": "Sri Venkateswara FMCG Supply"},
                {"field": "delay_days", "value": "2", "evidence": "two-day delay"},
                {"field": "product", "value": "Cooking oil 1 L pouch", "evidence": "Cooking oil 1 L pouch"},
            ],
            "unknowns": ["supplier-confirmed revised date"],
        },
    ),
    (
        "Lakshmi Provision Store says six biscuit packs arrived damaged in today's delivery.",
        {
            "intents": [{"intent": "damaged_item", "confidence": 0.9, "evidence": "arrived damaged"}],
            "facts": [
                {"field": "retailer_name", "value": "Lakshmi Provision Store", "evidence": "Lakshmi Provision Store"},
                {"field": "quantity", "value": "6", "evidence": "six"},
                {"field": "product", "value": "biscuit packs", "evidence": "biscuit packs"},
            ],
            "unknowns": ["order reference", "invoice reference"],
        },
    ),
)


def few_shot_suffix() -> str:
    parts = ["\n\nWorked examples. Use the same JSON shape and copy evidence exactly as written."]
    for text, payload in FEW_SHOT_EXAMPLES:
        parts.append(f"\nMessage:\n<<<\n{text}\n>>>\nJSON:\n{json.dumps(payload, ensure_ascii=False)}")
    return "".join(parts)


@dataclass(frozen=True)
class StrategySpec:
    name: str
    description: str
    few_shot: bool = False
    repair: bool = False


STRATEGIES: tuple[StrategySpec, ...] = (
    StrategySpec("rules", "Deterministic rules extractor; no model call."),
    StrategySpec("zero_shot", "Versioned system prompt with JSON mode."),
    StrategySpec(
        "few_shot",
        "Versioned system prompt plus two worked examples from fixture messages.",
        few_shot=True,
    ),
    StrategySpec(
        "zero_shot_repair",
        "Zero-shot prompt with one validation-guided repair call.",
        repair=True,
    ),
    StrategySpec(
        "few_shot_repair",
        "Few-shot prompt with one validation-guided repair call.",
        few_shot=True,
        repair=True,
    ),
)

Factory = Callable[[StrategySpec], Extractor]


def _system_prompt(spec: StrategySpec) -> str:
    return SYSTEM_PROMPT + (few_shot_suffix() if spec.few_shot else "")


def _prompt_version(spec: StrategySpec) -> str:
    return f"{EXTRACTION_PROMPT_VERSION}+{spec.name}"


def _default_factory() -> Factory:
    base = LLMExtractor.from_environment()
    if base is None:
        raise ExtractionEvaluationUnavailable("LLM extraction is not configured; only the rules strategy can run.")

    def build(spec: StrategySpec) -> Extractor:
        return LLMExtractor(
            base_url=base.base_url,
            api_key=base.api_key,
            model=base.model,
            timeout_seconds=base.timeout_seconds,
            ca_bundle=base.ca_bundle,
            json_mode=base.json_mode,
            system_prompt=_system_prompt(spec),
            prompt_version=_prompt_version(spec),
        )

    return build


def _message(record: dict, state: BusinessState) -> MessageSubmission:
    return MessageSubmission(
        message_id=record["message_id"],
        source_type="synthetic",
        text=record["text"],
        observed_at=state.as_of,
        language="unknown",
        state_version=record["state_version"],
    )


def _usage(extractor: Extractor) -> tuple[int | None, int | None]:
    usage = getattr(extractor, "last_usage", {}) or {}
    prompt = usage.get("prompt_tokens")
    completion = usage.get("completion_tokens")
    return (
        int(prompt) if isinstance(prompt, (int, float)) else None,
        int(completion) if isinstance(completion, (int, float)) else None,
    )


def estimate_cost(prompt_tokens: int | None, completion_tokens: int | None) -> float | None:
    """Priced only when an explicit illustrative rate is configured; never guessed."""
    rate = os.getenv(COST_RATE_ENV, "").strip()
    if not rate or prompt_tokens is None or completion_tokens is None:
        return None
    try:
        per_thousand = float(rate)
    except ValueError:
        return None
    return round((prompt_tokens + completion_tokens) / 1000.0 * per_thousand, 6)


def _failure_labels(
    result: dict, violations: list[str], error: str | None, fallback: bool
) -> list[str]:
    labels: list[str] = []
    if error:
        labels.append("tool_call_error")
    if violations:
        labels.append("hallucination" if any("verbatim" in item or "span" in item for item in violations) else "reasoning_error")
    if not result["intent_correct"]:
        labels.append("reasoning_error")
    if not all(result["entity_matches"].values()) and not labels:
        labels.append("hallucination")
    if fallback and "tool_call_error" not in labels:
        labels.append("tool_call_error")
    return sorted(set(labels))


def _rules_measurement(message: MessageSubmission, state: BusinessState, record: dict) -> dict:
    started = time.perf_counter()
    extraction = RulesExtractor().extract(message, state)
    violations = validate_extraction(extraction, message, state)
    latency_ms = (time.perf_counter() - started) * 1000
    result = score_extraction(extraction, record, latency_ms, violations, False, None)
    result.update(
        {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "estimated_cost": None,
            "calls": 0,
            "repair_attempted": False,
            "repair_succeeded": False,
            "failure_labels": _failure_labels(result, violations, None, False),
        }
    )
    return result


def _llm_measurement(
    extractor: Extractor,
    spec: StrategySpec,
    message: MessageSubmission,
    state: BusinessState,
    record: dict,
) -> dict:
    started = time.perf_counter()
    prompt_tokens = 0
    completion_tokens = 0
    calls = 0
    raw_extraction = None
    violations: list[str] = []
    error: str | None = None
    fallback = False
    repair_attempted = False
    repair_succeeded = False
    extraction = None

    try:
        raw_extraction = extractor.extract(message, state)
        calls += 1
        prompt, completion = _usage(extractor)
        prompt_tokens += prompt or 0
        completion_tokens += completion or 0
        extraction = raw_extraction
        violations = validate_extraction(extraction, message, state)
        if violations and spec.repair:
            repair_attempted = True
            repair_text = (
                message.text
                + "\n\nA previous extraction of this message failed these deterministic checks: "
                + "; ".join(violations)
                + ". Return corrected JSON for the message above. Include only facts whose evidence "
                "appears verbatim in the message."
            )
            repair_message = message.model_copy(update={"text": repair_text})
            repair_extraction = extractor.extract(repair_message, state)
            calls += 1
            prompt, completion = _usage(extractor)
            prompt_tokens += prompt or 0
            completion_tokens += completion or 0
            raw_extraction = repair_extraction
            repair_violations = validate_extraction(repair_extraction, message, state)
            if not repair_violations:
                extraction = repair_extraction
                violations = []
                repair_succeeded = True
            else:
                violations = repair_violations
        if violations:
            raise ValueError("Model output failed deterministic validation")
    except Exception as exc:  # noqa: BLE001 - failures are measured, not crashes
        fallback = True
        error = f"{type(exc).__name__}: {exc}"
        extraction = RulesExtractor().extract(message, state)
        validate_extraction(extraction, message, state)
        extraction.uncertainties.append(
            "Model extraction was unavailable or failed validation; deterministic rules were used."
        )

    latency_ms = (time.perf_counter() - started) * 1000
    result = score_extraction(extraction, record, latency_ms, violations, fallback, error, raw_extraction)
    result.update(
        {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "estimated_cost": estimate_cost(prompt_tokens, completion_tokens),
            "calls": calls,
            "repair_attempted": repair_attempted,
            "repair_succeeded": repair_succeeded,
            "failure_labels": _failure_labels(result, violations, error, fallback),
        }
    )
    return result


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    index = max(math.ceil(len(ordered) * percentile) - 1, 0)
    return ordered[index]


def _summarise(rows: list[dict], strategy: str) -> dict:
    results = [row["results"][strategy] for row in rows]
    entity_total = sum(result["entity_total"] for result in results)
    present_total = sum(result["present_entity_total"] for result in results)
    latencies = [result["latency_ms"] for result in results]
    prompt_tokens = sum(result["prompt_tokens"] for result in results)
    completion_tokens = sum(result["completion_tokens"] for result in results)
    costs = [result["estimated_cost"] for result in results]
    priced = all(cost is not None for cost in costs)
    labels: dict[str, int] = {}
    for result in results:
        for label in result["failure_labels"]:
            labels[label] = labels.get(label, 0) + 1
    return {
        "examples": len(results),
        "intent_accuracy": sum(result["intent_correct"] for result in results) / len(results),
        "stated_entity_accuracy": (
            sum(result["present_entity_correct"] for result in results) / present_total if present_total else None
        ),
        "record_exact_match": sum(result["record_exact"] for result in results) / len(results),
        "validation_pass_rate": sum(result["validation_passed"] for result in results) / len(results),
        "fallback_count": sum(result["fallback"] for result in results),
        "error_count": sum(1 for result in results if result["error"]),
        "repair_attempts": sum(result["repair_attempted"] for result in results),
        "repair_successes": sum(result["repair_succeeded"] for result in results),
        "model_calls": sum(result["calls"] for result in results),
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
        "tokens_per_example": round((prompt_tokens + completion_tokens) / len(results), 1),
        "estimated_cost": round(sum(costs), 6) if priced else None,
        "latency_ms_p50": round(statistics.median(latencies), 2),
        "latency_ms_p95": round(_percentile(latencies, 0.95), 2),
        "failure_labels": labels,
        "entity_total": entity_total,
    }


def run_prompting_evaluation(
    *,
    factory: Factory | None = None,
    records: list[dict] | None = None,
    strategies: tuple[StrategySpec, ...] | None = None,
    progress: Callable[[dict], None] | None = None,
) -> dict:
    """Compare prompting strategies on the held-out set. Rules always run; LLM specs need a factory."""
    records = records if records is not None else load_held_out_records()
    state = load_business_state(expected_version=records[0]["state_version"])
    chosen = strategies if strategies is not None else STRATEGIES
    llm_specs = [spec for spec in chosen if spec.name != "rules"]
    build = factory
    llm_available = True
    if build is None and llm_specs:
        try:
            build = _default_factory()
        except ExtractionEvaluationUnavailable:
            llm_available = False

    rows: list[dict] = []
    model_name = None
    for position, record in enumerate(records, start=1):
        message = _message(record, state)
        row = {"message_id": record["message_id"], "text": record["text"], "results": {}}
        if any(spec.name == "rules" for spec in chosen):
            row["results"]["rules"] = _rules_measurement(message, state, record)
        if llm_available and build is not None:
            for spec in llm_specs:
                extractor = build(spec)
                if model_name is None:
                    model_name = getattr(extractor, "model", None)
                row["results"][spec.name] = _llm_measurement(extractor, spec, message, state, record)
        rows.append(row)
        if progress:
            progress(
                {
                    "step": "example_completed",
                    "title": f"{record['message_id']}: {len(row['results'])} strategies scored",
                    "position": position,
                    "current": position,
                    "total": len(records),
                    "detail": record["text"],
                    "row": row,
                }
            )

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset": str(HELD_OUT.relative_to(Path(__file__).resolve().parents[2])),
        "dataset_sha256": hashlib.sha256(HELD_OUT.read_bytes()).hexdigest(),
        "examples": len(records),
        "split": "held_out",
        "llm_available": llm_available,
        "model": model_name,
        "prompt_base_version": EXTRACTION_PROMPT_VERSION,
        "cost_rate_env": COST_RATE_ENV,
        "cost_pricing": (
            "Estimated from gateway-reported tokens and the configured illustrative rate."
            if os.getenv(COST_RATE_ENV, "").strip()
            else "Not priced: no illustrative rate configured. Token counts are gateway-reported."
        ),
        "strategies": {
            name: _summarise(rows, name)
            for name in (spec.name for spec in chosen)
            if any(name in row["results"] for row in rows)
        },
    }
    return {"summary": summary, "rows": rows}


def summarize(result: dict) -> str:
    summary = result["summary"]
    lines = [
        f"Prompting comparison · {summary['examples']} held-out examples · model {summary['model'] or 'rules only'}",
        f"Dataset sha256: {summary['dataset_sha256']}",
        "",
        f"{'strategy':18} {'intent':>7} {'stated':>7} {'exact':>7} {'fallback':>9} {'tokens':>8} {'p50 ms':>8}",
    ]
    for name, values in summary["strategies"].items():
        stated = f"{values['stated_entity_accuracy']:.1%}" if values["stated_entity_accuracy"] is not None else "n/a"
        lines.append(
            f"{name:18} {values['intent_accuracy']:>7.1%} {stated:>7} {values['record_exact_match']:>7.1%} "
            f"{values['fallback_count']:>9} {values['total_tokens']:>8} {values['latency_ms_p50']:>8.1f}"
        )
    lines.append("")
    lines.append(summary["cost_pricing"])
    return "\n".join(lines)
