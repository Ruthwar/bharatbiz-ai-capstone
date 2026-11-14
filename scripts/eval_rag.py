"""Measure whether retrieval earns its place.

Reports, on the golden query set:
  - primary@1: the expected document is the first hit
  - recall@3 / recall@5: expected or an accepted alternative is inside the top k
  - MRR: mean reciprocal rank of the expected document
  - a naive term-frequency baseline on the same queries, so the gain is visible
  - latency, corpus size, and citation coverage on the SCN-003 review card

Run: python scripts/eval_rag.py [--json]
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from pathlib import Path

os.environ.setdefault("LLM_PROVIDER", "none")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.rag.corpus import load_documents  # noqa: E402
from app.rag.retrieval import RagIndex, _tokens  # noqa: E402

GOLDEN = PROJECT_ROOT / "data" / "eval" / "golden_queries.json"


def _naive_baseline() -> dict[str, str]:
    """Term counting over the whole document, the obvious thing to do without BM25."""
    corpus = {document.document_id: f"{document.title}\n" + "\n".join(s.text for s in document.sections)
              for document in load_documents()}
    return corpus


def _baseline_rank(query: str, corpus: dict[str, str], top_k: int) -> list[str]:
    tokens = _tokens(query)
    scored = []
    for document_id, text in corpus.items():
        lowered = text.lower()
        score = sum(lowered.count(token) for token in tokens)
        scored.append((score, document_id))
    scored.sort(key=lambda row: (-row[0], row[1]))
    return [document_id for score, document_id in scored if score > 0][:top_k]


def evaluate(index: RagIndex, golden: dict) -> dict:
    queries = golden["queries"]
    corpus = _naive_baseline()
    rows = []
    latencies = []
    for case in queries:
        started = time.perf_counter()
        hits = index.search(case["query"], top_k=5)
        latencies.append((time.perf_counter() - started) * 1000)
        ranked = [hit["document_id"] for hit in hits]
        accepted = {case["expected"], *case.get("acceptable", [])}
        baseline = _baseline_rank(case["query"], corpus, 5)
        rows.append(
            {
                "id": case["id"],
                "expected": case["expected"],
                "ranked": ranked,
                "primary_at_1": bool(ranked) and ranked[0] == case["expected"],
                "hit_at_3": bool(accepted & set(ranked[:3])),
                "hit_at_5": bool(accepted & set(ranked[:5])),
                "reciprocal_rank": (
                    1 / (ranked.index(case["expected"]) + 1) if case["expected"] in ranked else 0.0
                ),
                "baseline_at_3": bool(accepted & set(baseline[:3])),
                "baseline_primary_at_1": bool(baseline) and baseline[0] == case["expected"],
                "baseline_reciprocal_rank": (
                    1 / (baseline.index(case["expected"]) + 1) if case["expected"] in baseline else 0.0
                ),
            }
        )
    total = len(rows)
    return {
        "queries": total,
        "primary_at_1": sum(row["primary_at_1"] for row in rows) / total,
        "recall_at_3": sum(row["hit_at_3"] for row in rows) / total,
        "recall_at_5": sum(row["hit_at_5"] for row in rows) / total,
        "mrr": sum(row["reciprocal_rank"] for row in rows) / total,
        "baseline_primary_at_1": sum(row["baseline_primary_at_1"] for row in rows) / total,
        "baseline_recall_at_3": sum(row["baseline_at_3"] for row in rows) / total,
        "baseline_mrr": sum(row["baseline_reciprocal_rank"] for row in rows) / total,
        "latency_ms_p50": statistics.median(latencies),
        "latency_ms_p95": sorted(latencies)[max(int(len(latencies) * 0.95) - 1, 0)],
        "misses": [row["id"] for row in rows if not row["hit_at_5"]],
        "rows": rows,
    }


def citation_coverage(index: RagIndex) -> dict:
    """Open a real SCN-003 review and check that the reviewer was given checkable clauses."""
    from app.orchestration.review import build_review_context
    from app.orchestration.workflow import process_message
    from app.schemas.contracts import MessageSubmission

    fixture = json.loads(
        (PROJECT_ROOT / "data" / "synthetic" / "scenario_fixtures" / "SCN-003.json").read_text(encoding="utf-8")
    )
    result = process_message(MessageSubmission.model_validate(fixture["message"]))
    context = build_review_context(result) or {}
    references = context.get("references") or []
    return {
        "references": len(references),
        "with_provenance": sum(
            1 for ref in references if ref["document_id"] and ref["effective_from"] and ref["licence"]
        ),
        "with_quote": sum(1 for ref in references if ref["quote"]),
        "effective_by_scenario_date": sum(1 for ref in references if ref["effective_from"] <= "2026-11-01"),
        "error": context.get("references_error"),
        "document_ids": [ref["document_id"] for ref in references],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="print machine-readable results")
    args = parser.parse_args()

    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    documents = load_documents()
    index = RagIndex(":memory:")
    index.ensure()
    metrics = evaluate(index, golden)
    citations = citation_coverage(index)
    size = sum(path.stat().st_size for path in (PROJECT_ROOT / "data" / "knowledge_docs").glob("*.md"))

    summary = {
        "corpus_documents": len(documents),
        "corpus_sections": sum(len(document.sections) for document in documents),
        "corpus_bytes": size,
        **{key: value for key, value in metrics.items() if key != "rows"},
        "citation_coverage": citations,
    }

    if args.json:
        print(json.dumps({"summary": summary, "rows": metrics["rows"]}, indent=2))
        return 0

    print(f"Corpus: {summary['corpus_documents']} documents, {summary['corpus_sections']} sections, "
          f"{size / 1024:.1f} KiB")
    print(f"Queries: {metrics['queries']}\n")
    print(f"{'id':6} {'expected':20} {'rank':4} {'top-3 doc':22} {'baseline@3'}")
    for row in metrics["rows"]:
        top = row["ranked"][0] if row["ranked"] else "-"
        print(f"{row['id']:6} {row['expected']:20} {row['ranked'].index(row['expected']) + 1 if row['expected'] in row['ranked'] else '-':>4} "
              f"{top:22} {'hit' if row['baseline_at_3'] else 'miss'}")
    print()
    print(f"primary@1      {metrics['primary_at_1']:.1%}")
    print(f"recall@3       {metrics['recall_at_3']:.1%}")
    print(f"recall@5       {metrics['recall_at_5']:.1%}")
    print(f"MRR            {metrics['mrr']:.3f}")
    print(f"baseline@1     {metrics['baseline_primary_at_1']:.1%}  (term frequency, no BM25)")
    print(f"baseline@3     {metrics['baseline_recall_at_3']:.1%}")
    print(f"baseline MRR   {metrics['baseline_mrr']:.3f}")
    print(f"latency p50    {metrics['latency_ms_p50']:.1f} ms   p95 {metrics['latency_ms_p95']:.1f} ms")
    print(f"misses@5       {metrics['misses'] or 'none'}")
    print()
    print("SCN-003 review card citations: "
          f"{citations['references']} references, {citations['with_provenance']} with provenance, "
          f"{citations['with_quote']} with a quote, {citations['effective_by_scenario_date']} in force "
          f"on 2026-11-01")
    print("documents:", ", ".join(citations["document_ids"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
