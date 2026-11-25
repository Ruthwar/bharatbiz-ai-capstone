"""Measure retrieval quality. Run: python scripts/eval_rag.py [--json]."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("LLM_PROVIDER", "none")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.evaluation.rag import citation_coverage, evaluate, run_rag_evaluation  # noqa: E402,F401


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="print machine-readable results")
    args = parser.parse_args()
    result = run_rag_evaluation()
    summary = result["summary"]
    rows = result["rows"]
    citations = summary["citation_coverage"]

    if args.json:
        print(json.dumps(result, indent=2))
        return 0

    print(
        f"Corpus: {summary['corpus_documents']} documents, {summary['corpus_sections']} sections, "
        f"{summary['corpus_bytes'] / 1024:.1f} KiB"
    )
    print(f"Queries: {summary['queries']}\n")
    print(f"{'id':6} {'expected':20} {'rank':4} {'top-3 doc':22} {'baseline@3'}")
    for row in rows:
        top = row["ranked"][0] if row["ranked"] else "-"
        rank = row["ranked"].index(row["expected"]) + 1 if row["expected"] in row["ranked"] else "-"
        print(f"{row['id']:6} {row['expected']:20} {rank:>4} {top:22} {'hit' if row['baseline_at_3'] else 'miss'}")
    print()
    print(f"primary@1      {summary['primary_at_1']:.1%}")
    print(f"recall@3       {summary['recall_at_3']:.1%}")
    print(f"recall@5       {summary['recall_at_5']:.1%}")
    print(f"MRR            {summary['mrr']:.3f}")
    print(f"baseline@1     {summary['baseline_primary_at_1']:.1%}  (term frequency, no BM25)")
    print(f"baseline@3     {summary['baseline_recall_at_3']:.1%}")
    print(f"baseline MRR   {summary['baseline_mrr']:.3f}")
    print(f"latency p50    {summary['latency_ms_p50']:.1f} ms   p95 {summary['latency_ms_p95']:.1f} ms")
    print(f"misses@5       {summary['misses'] or 'none'}")
    print()
    print(
        "SCN-003 review card citations: "
        f"{citations['references']} references, {citations['with_provenance']} with provenance, "
        f"{citations['with_quote']} with a quote, {citations['effective_by_scenario_date']} in force on 2026-11-01"
    )
    print("documents:", ", ".join(citations["document_ids"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
