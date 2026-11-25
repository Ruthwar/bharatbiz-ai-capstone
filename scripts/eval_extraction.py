"""Evaluate frozen held-out extraction labels. Run: python scripts/eval_extraction.py [--json]."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.evaluation.extraction import ExtractionEvaluationUnavailable, run_extraction_evaluation  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="print machine-readable results")
    args = parser.parse_args()
    try:
        result = run_extraction_evaluation()
    except ExtractionEvaluationUnavailable as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(result, indent=2))
        return 0

    summary = result["summary"]
    print(f"Held-out messages: {summary['examples']} · model: {summary['llm_model']}")
    print(f"Prompt: {summary['prompt_version']} · taxonomy: {summary['taxonomy_version']}\n")
    for variant, label in (("rules", "Rules"), ("llm", "LLM pipeline")):
        metrics = summary["variants"][variant]
        print(label)
        print(f"  intent accuracy:       {metrics['intent_accuracy']:.1%}")
        print(f"  entity exact match:    {metrics['entity_exact_match']:.1%}")
        stated = metrics["stated_entity_accuracy"]
        print(f"  stated-fact accuracy:  {stated:.1%}" if stated is not None else "  stated-fact accuracy:  n/a")
        print(f"  exact record match:    {metrics['record_exact_match']:.1%}")
        print(f"  validation pass rate:  {metrics['validation_pass_rate']:.1%}")
        print(f"  fallbacks:             {metrics['fallback_count']}")
        print(f"  latency p50 / p95:     {metrics['latency_ms_p50']:.0f} / {metrics['latency_ms_p95']:.0f} ms\n")
    print("Per-message outcomes")
    for row in result["rows"]:
        llm = row["results"]["llm"]
        print(
            f"{row['message_id']}: expected={row['expected_intent']} predicted={llm['predicted_intent']} "
            f"entities={llm['entity_correct']}/{llm['entity_total']} fallback={llm['fallback']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
