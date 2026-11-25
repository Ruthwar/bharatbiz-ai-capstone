"""Measured retrieval ablations on the additive Track B corpus.

Every strategy is scored on the same frozen 40 golden queries with the same metrics used by
scripts/eval_rag.py. The runtime corpus and the runtime BM25 index are measured first and are
never modified by this module.
"""

from __future__ import annotations

import gc
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from app.evaluation.rag import evaluate
from app.rag.corpus import DEFAULT_CORPUS_DIR, TRACK_B_CORPUS_DIR, load_documents
from app.rag.hybrid import EMBEDDING_NAME, ChunkIndex
from app.rag.retrieval import RagIndex

PROJECT_ROOT = Path(__file__).resolve().parents[2]
GOLDEN = PROJECT_ROOT / "data" / "eval" / "golden_queries.json"

BASE_STRATEGY = "base_section_bm25"


def _golden() -> tuple[dict, str]:
    payload = GOLDEN.read_bytes()
    return json.loads(payload.decode("utf-8")), hashlib.sha256(payload).hexdigest()


def _metrics(result: dict) -> dict:
    keys = (
        "queries",
        "primary_at_1",
        "recall_at_3",
        "recall_at_5",
        "mrr",
        "latency_ms_p50",
        "latency_ms_p95",
        "misses",
    )
    return {key: result[key] for key in keys}


def _record(
    strategy_id: str,
    *,
    corpus: str,
    chunking: str,
    retrieval: str,
    documents: int,
    chunks: int | None,
    build_ms: float,
    result: dict,
) -> dict:
    return {
        "id": strategy_id,
        "corpus": corpus,
        "chunking": chunking,
        "retrieval": retrieval,
        "documents": documents,
        "chunks": chunks,
        "build_ms": round(build_ms, 2),
        "metrics": _metrics(result),
        "rows": result["rows"],
    }


def run_rag_experiments(progress: Callable[[dict], None] | None = None) -> dict:
    golden, golden_sha = _golden()
    base_documents = load_documents(DEFAULT_CORPUS_DIR)
    if not TRACK_B_CORPUS_DIR.is_dir():
        raise FileNotFoundError(
            f"Track B corpus missing at {TRACK_B_CORPUS_DIR}; run scripts/build_track_b_corpus.py --write"
        )
    expanded_documents = load_documents(DEFAULT_CORPUS_DIR, extra_roots=[TRACK_B_CORPUS_DIR])
    if len(expanded_documents) <= len(base_documents):
        raise ValueError("Expanded corpus did not add documents")

    plans = (
        ("section", "section", ("bm25", "bm25_rerank", "dense", "hybrid", "hybrid_rerank")),
        ("paragraph", "paragraph", ("bm25", "bm25_rerank", "hybrid_rerank")),
        ("fixed", "fixed", ("bm25", "bm25_rerank", "hybrid_rerank")),
    )
    total = 1 + sum(len(modes) for _, _, modes in plans)
    if progress:
        progress(
            {
                "step": "dataset_loaded",
                "title": f"Loaded {len(base_documents)} base and {len(expanded_documents)} expanded documents",
                "current": 0,
                "total": total,
                "detail": f"{len(golden['queries'])} frozen golden queries; embedding {EMBEDDING_NAME}.",
            }
        )

    base_size = sum(path.stat().st_size for path in DEFAULT_CORPUS_DIR.glob("*.md"))
    expanded_size = base_size + sum(path.stat().st_size for path in TRACK_B_CORPUS_DIR.glob("*.md"))
    strategies: list[dict] = []

    started = time.perf_counter()
    base_index = RagIndex(":memory:")
    base_index.ensure()
    base_build = (time.perf_counter() - started) * 1000
    base_result = evaluate(base_index, golden)
    strategies.append(
        _record(
            BASE_STRATEGY,
            corpus="base",
            chunking="section",
            retrieval="bm25",
            documents=len(base_documents),
            chunks=sum(len(document.sections) for document in base_documents),
            build_ms=base_build,
            result=base_result,
        )
    )
    if progress:
        progress(
            {
                "step": "strategy_completed",
                "title": f"{BASE_STRATEGY}: recall@3 {base_result['recall_at_3']:.1%}",
                "current": len(strategies),
                "total": total,
                "detail": "Runtime corpus and runtime BM25 index measured unchanged.",
            }
        )
    del base_index
    gc.collect()

    for chunking, label, retrieval_modes in plans:
        started = time.perf_counter()
        index = ChunkIndex.from_documents(expanded_documents, chunking)
        index._connect()  # build the FTS table up front so build time is separated from query time
        index.vectors()
        build_ms = (time.perf_counter() - started) * 1000
        for retrieval in retrieval_modes:
            strategy_id = f"expanded_{label}_{retrieval}"
            result = evaluate(_StrategyView(index, retrieval), golden)
            strategies.append(
                _record(
                    strategy_id,
                    corpus="expanded",
                    chunking=chunking,
                    retrieval=retrieval,
                    documents=len(expanded_documents),
                    chunks=len(index.chunks),
                    build_ms=build_ms,
                    result=result,
                )
            )
            if progress:
                progress(
                    {
                        "step": "strategy_completed",
                        "title": f"{strategy_id}: recall@3 {result['recall_at_3']:.1%}",
                        "current": len(strategies),
                        "total": total,
                        "detail": (
                            f"{chunking} chunks · {retrieval} · {len(result['rows'])} frozen queries · "
                            f"primary@1 {result['primary_at_1']:.1%}"
                        ),
                    }
                )
        del index
        gc.collect()

    base = strategies[0]["metrics"]
    for strategy in strategies:
        strategy["delta_vs_base"] = {
            "recall_at_3": round(strategy["metrics"]["recall_at_3"] - base["recall_at_3"], 4),
            "primary_at_1": round(strategy["metrics"]["primary_at_1"] - base["primary_at_1"], 4),
            "mrr": round(strategy["metrics"]["mrr"] - base["mrr"], 4),
        }

    ranked = sorted(
        strategies,
        key=lambda item: (item["metrics"]["recall_at_3"], item["metrics"]["mrr"]),
        reverse=True,
    )
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "golden_queries_sha256": golden_sha,
        "golden_queries": len(golden["queries"]),
        "embedding": EMBEDDING_NAME,
        "config": {
            "top_k": 5,
            "rrf_k": 60,
            "chunk_paragraph_max_words": 180,
            "chunk_fixed_words": 160,
            "chunk_fixed_overlap": 40,
            "rerank_weights": {
                "query_coverage": 0.35,
                "heading_coverage": 0.15,
                "bigram_coverage": 0.10,
                "dense_cosine": 0.25,
                "rrf_fusion": 0.15,
            },
        },
        "base_corpus": {
            "documents": len(base_documents),
            "sections": sum(len(document.sections) for document in base_documents),
            "bytes": base_size,
        },
        "expanded_corpus": {
            "documents": len(expanded_documents),
            "sections": sum(len(document.sections) for document in expanded_documents),
            "bytes": expanded_size,
            "additive_documents": len(expanded_documents) - len(base_documents),
        },
        "strategies": strategies,
        "best_by_recall_at_3": ranked[0]["id"],
        "notes": [
            "The embedding is deterministic lexical hashing, not a semantic sentence model.",
            "The runtime citation corpus and BM25 path are unchanged; the expanded corpus is opt-in.",
            "Recall@3 counts a hit when the expected or an acceptable document appears in the top three.",
        ],
    }


class _StrategyView:
    """Adapt a ChunkIndex to the search signature used by app.evaluation.rag.evaluate."""

    def __init__(self, index: ChunkIndex, strategy: str):
        self._index = index
        self._strategy = strategy

    def search(self, query: str, top_k: int = 5, **kwargs) -> list[dict]:
        return self._index.search(query, top_k=top_k, strategy=self._strategy, **kwargs)


def summarize(result: dict) -> str:
    base = result["strategies"][0]
    lines = [
        f"Golden queries: {result['golden_queries']}   sha256 {result['golden_queries_sha256'][:12]}",
        f"Base corpus: {result['base_corpus']['documents']} docs / {result['base_corpus']['sections']} sections",
        (
            f"Expanded corpus: {result['expanded_corpus']['documents']} docs / "
            f"{result['expanded_corpus']['sections']} sections "
            f"(+{result['expanded_corpus']['additive_documents']})"
        ),
        f"Embedding: {result['embedding']}",
        "",
        f"{'strategy':38} {'chunks':>7} {'P@1':>6} {'R@3':>6} {'R@5':>6} {'MRR':>6} {'p95 ms':>7}",
    ]
    for strategy in result["strategies"]:
        metrics = strategy["metrics"]
        lines.append(
            f"{strategy['id']:38} {strategy['chunks'] or '-':>7} "
            f"{metrics['primary_at_1']:6.1%} {metrics['recall_at_3']:6.1%} {metrics['recall_at_5']:6.1%} "
            f"{metrics['mrr']:6.3f} {metrics['latency_ms_p95']:7.1f}"
        )
    lines.extend(["", f"Best recall@3: {result['best_by_recall_at_3']}"])
    changed = [
        strategy["id"]
        for strategy in result["strategies"]
        if strategy["metrics"]["recall_at_3"] < base["metrics"]["recall_at_3"]
    ]
    lines.append(f"Below the runtime base on recall@3: {', '.join(changed) if changed else 'none'}")
    return "\n".join(lines)
