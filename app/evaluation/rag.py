from __future__ import annotations

import json
import math
import statistics
import time
from pathlib import Path
from typing import Callable

from app.extraction.rules import RulesExtractor
from app.rag.corpus import load_documents
from app.rag.retrieval import RagIndex, _tokens

PROJECT_ROOT = Path(__file__).resolve().parents[2]
GOLDEN = PROJECT_ROOT / "data" / "eval" / "golden_queries.json"
Progress = Callable[[dict], None]


def _emit(progress: Progress | None, step: str, title: str, **fields) -> None:
    if progress:
        progress({"step": step, "title": title, **fields})


def _naive_baseline() -> dict[str, str]:
    return {
        document.document_id: f"{document.title}\n" + "\n".join(section.text for section in document.sections)
        for document in load_documents()
    }


def _baseline_rank(query: str, corpus: dict[str, str], top_k: int) -> list[str]:
    tokens = _tokens(query)
    scored = []
    for document_id, text in corpus.items():
        lowered = text.lower()
        score = sum(lowered.count(token) for token in tokens)
        scored.append((score, document_id))
    scored.sort(key=lambda row: (-row[0], row[1]))
    return [document_id for score, document_id in scored if score > 0][:top_k]


def evaluate(index: RagIndex, golden: dict, progress: Progress | None = None) -> dict:
    queries = golden["queries"]
    corpus = _naive_baseline()
    rows = []
    latencies = []
    total = len(queries)
    for position, case in enumerate(queries, start=1):
        _emit(
            progress,
            "query_started",
            f"Retrieving for {case['id']} ({position}/{total})",
            current=position,
            total=total,
            detail=case["query"],
        )
        started = time.perf_counter()
        hits = index.search(case["query"], top_k=5)
        latency_ms = (time.perf_counter() - started) * 1000
        latencies.append(latency_ms)
        ranked = [hit["document_id"] for hit in hits]
        accepted = {case["expected"], *case.get("acceptable", [])}
        baseline = _baseline_rank(case["query"], corpus, 5)
        row = {
            "id": case["id"],
            "query": case["query"],
            "expected": case["expected"],
            "acceptable": sorted(accepted),
            "ranked": ranked,
            "hits": [
                {
                    key: hit.get(key)
                    for key in (
                        "document_id",
                        "title",
                        "section_id",
                        "heading",
                        "quote",
                        "effective_from",
                        "licence",
                        "score",
                    )
                }
                for hit in hits
            ],
            "primary_at_1": bool(ranked) and ranked[0] == case["expected"],
            "hit_at_3": bool(accepted & set(ranked[:3])),
            "hit_at_5": bool(accepted & set(ranked[:5])),
            "reciprocal_rank": 1 / (ranked.index(case["expected"]) + 1) if case["expected"] in ranked else 0.0,
            "baseline_at_3": bool(accepted & set(baseline[:3])),
            "baseline_primary_at_1": bool(baseline) and baseline[0] == case["expected"],
            "baseline_reciprocal_rank": (
                1 / (baseline.index(case["expected"]) + 1) if case["expected"] in baseline else 0.0
            ),
            "latency_ms": latency_ms,
        }
        rows.append(row)
        _emit(
            progress,
            "query_completed",
            f"{case['id']}: {'passed' if row['hit_at_3'] else 'missed'} recall@3",
            current=position,
            total=total,
            detail=f"Expected {case['expected']}; retrieved {', '.join(ranked[:3]) or 'no documents'}.",
            outcome="passed" if row["hit_at_3"] else "failed",
            row=row,
        )
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
        "latency_ms_p95": sorted(latencies)[max(math.ceil(len(latencies) * 0.95) - 1, 0)],
        "misses": [row["id"] for row in rows if not row["hit_at_5"]],
        "rows": rows,
    }


def citation_coverage(index: RagIndex, progress: Progress | None = None) -> dict:
    from app.orchestration.review import build_review_context
    from app.orchestration.workflow import process_message
    from app.schemas.contracts import MessageSubmission

    _emit(progress, "citations_started", "Checking SCN-003 review citations", detail="Processing the fixture with deterministic rules extraction.")
    fixture = json.loads(
        (PROJECT_ROOT / "data" / "synthetic" / "scenario_fixtures" / "SCN-003.json").read_text(encoding="utf-8")
    )
    result = process_message(MessageSubmission.model_validate(fixture["message"]), extractor=RulesExtractor())
    context = build_review_context(result) or {}
    references = context.get("references") or []
    scenario_date = fixture["message"]["observed_at"][:10]
    coverage = {
        "references": len(references),
        "with_provenance": sum(
            1 for reference in references if reference["document_id"] and reference["effective_from"] and reference["licence"]
        ),
        "with_quote": sum(1 for reference in references if reference["quote"]),
        "effective_by_scenario_date": sum(1 for reference in references if reference["effective_from"] <= scenario_date),
        "error": context.get("references_error"),
        "document_ids": [reference["document_id"] for reference in references],
    }
    _emit(
        progress,
        "citations_completed",
        "Citation coverage checked",
        detail=f"{coverage['with_quote']}/{coverage['references']} references contain verbatim quotes.",
        outcome="passed" if coverage["references"] and coverage["with_quote"] == coverage["references"] else "failed",
    )
    return coverage


def run_rag_evaluation(progress: Progress | None = None) -> dict:
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    documents = load_documents()
    _emit(
        progress,
        "dataset_loaded",
        f"Loaded {len(golden['queries'])} frozen golden queries",
        total=len(golden["queries"]),
        detail=f"Indexing {len(documents)} approved documents with SQLite FTS5 and BM25.",
    )
    index = RagIndex(":memory:")
    index.ensure()
    metrics = evaluate(index, golden, progress)
    citations = citation_coverage(index, progress)
    size = sum(path.stat().st_size for path in (PROJECT_ROOT / "data" / "knowledge_docs").glob("*.md"))
    summary = {
        "corpus_documents": len(documents),
        "corpus_sections": sum(len(document.sections) for document in documents),
        "corpus_bytes": size,
        **{key: value for key, value in metrics.items() if key != "rows"},
        "citation_coverage": citations,
    }
    _emit(progress, "metrics_completed", "RAG metrics calculated", detail="Computed ranking quality, baseline comparison, latency and citation coverage.", outcome="passed")
    return {"summary": summary, "rows": metrics["rows"]}
