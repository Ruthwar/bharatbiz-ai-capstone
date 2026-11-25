from __future__ import annotations

import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pytest

from app.evaluation.rag import evaluate
from app.rag.corpus import DEFAULT_CORPUS_DIR, TRACK_B_CORPUS_DIR, load_documents
from app.rag.hybrid import (
    EMBEDDING_DIM,
    Chunk,
    ChunkIndex,
    embed,
    fixed_chunks,
    paragraph_chunks,
    section_chunks,
)
from app.rag.retrieval import (
    RagIndex,
    _tokens,
    corpus_fingerprint,
    get_index,
    reset_index,
    retrieve,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
GOLDEN = json.loads((PROJECT_ROOT / "data" / "eval" / "golden_queries.json").read_text(encoding="utf-8"))
TRACK_B_MANIFEST = TRACK_B_CORPUS_DIR / "manifest.json"


def test_generated_corpus_is_current():
    completed = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "scripts" / "build_track_b_corpus.py"), "--check"],
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_generated_corpus_has_the_declared_shape():
    manifest = json.loads(TRACK_B_MANIFEST.read_text(encoding="utf-8"))
    assert manifest["document_count"] == 480
    assert manifest["base_corpus_documents"] == 33
    assert manifest["combined_document_count"] == 513
    assert manifest["classification"] == "synthetic"
    assert manifest["subordinate_to"] == "data/knowledge_docs/"
    assert sum(manifest["families"].values()) == manifest["document_count"]
    assert len(manifest["documents"]) == manifest["document_count"]


def test_additive_documents_parse_and_carry_provenance():
    base = load_documents()
    expanded = load_documents(DEFAULT_CORPUS_DIR, extra_roots=[TRACK_B_CORPUS_DIR])
    assert len(expanded) == len(base) + 480
    assert len({document.document_id for document in expanded}) == len(expanded)

    base_ids = {document.document_id for document in base}
    for document in expanded:
        if document.document_id in base_ids:
            continue
        assert document.classification == "synthetic"
        assert document.status in {"approved", "reference"}
        assert document.licence
        assert date.fromisoformat(document.effective_from)
        assert document.sections
        assert document.source_url == ""
        assert any("SIMULATION ONLY" in section.text.upper() for section in document.sections)

    section_ids = [section.section_id for document in expanded for section in document.sections]
    assert len(section_ids) == len(set(section_ids))


def test_default_runtime_corpus_is_unchanged():
    documents = load_documents()
    assert len(documents) == 33
    assert sum(len(document.sections) for document in documents) == 203
    manifest = json.loads((DEFAULT_CORPUS_DIR / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["document_count"] == 33


def test_default_index_stays_on_the_curated_corpus():
    index = RagIndex(":memory:")
    index.ensure()
    assert index.document_meta("POL-DLY-001") is not None
    assert index.document_meta("TB-CASE-001") is None


def test_expanded_index_adds_track_b_documents_without_losing_the_base():
    index = RagIndex(":memory:", extra_corpus_dirs=[TRACK_B_CORPUS_DIR])
    index.ensure()
    assert index.document_meta("POL-DLY-001") is not None
    assert index.document_meta("TB-CASE-001") is not None
    hits = index.search("Ameerpet area addendum supplier delay response", top_k=3)
    assert hits
    assert all(hit["licence"] for hit in hits)


def test_content_fingerprint_ignores_mtime_and_tracks_bytes(tmp_path):
    first = tmp_path / "one"
    second = tmp_path / "two"
    first.mkdir()
    second.mkdir()
    body = "---\ndocument_id: X\n---\nbody\n"
    (first / "X.md").write_text(body, encoding="utf-8")
    (second / "X.md").write_text(body, encoding="utf-8")
    assert corpus_fingerprint(first) == corpus_fingerprint(second)

    (second / "X.md").write_text(body + "changed\n", encoding="utf-8")
    assert corpus_fingerprint(first) != corpus_fingerprint(second)


def test_env_opt_in_adds_documents_and_reset_restores_default(monkeypatch):
    monkeypatch.setenv("BHARATBIZ_RAG_DB", ":memory:")
    monkeypatch.setenv("BHARATBIZ_RAG_CORPUS", str(TRACK_B_CORPUS_DIR))
    reset_index()
    try:
        assert get_index().document_meta("TB-CASE-001") is not None
    finally:
        monkeypatch.delenv("BHARATBIZ_RAG_CORPUS")
        reset_index()
    assert get_index().document_meta("TB-CASE-001") is None


def test_runtime_retrieve_defaults_to_bm25(monkeypatch):
    monkeypatch.setenv("BHARATBIZ_RAG_DB", ":memory:")
    monkeypatch.delenv("BHARATBIZ_RAG_STRATEGY", raising=False)
    monkeypatch.delenv("BHARATBIZ_RAG_CORPUS", raising=False)
    reset_index()
    try:
        query = "Rule 6 declarations on every package"
        assert retrieve(query, top_k=1) == get_index().search(query, top_k=1)
        monkeypatch.setenv("BHARATBIZ_RAG_STRATEGY", "not-a-strategy")
        reset_index()
        assert retrieve(query, top_k=1) == get_index().search(query, top_k=1)
    finally:
        reset_index()


def test_chunking_is_deterministic_and_preserves_edges():
    documents = load_documents(DEFAULT_CORPUS_DIR, extra_roots=[TRACK_B_CORPUS_DIR])
    sections = section_chunks(documents)
    assert len(sections) == sum(len(document.sections) for document in documents)
    assert len({chunk.chunk_id for chunk in sections}) == len(sections)

    for builder in (paragraph_chunks, fixed_chunks):
        first = builder(documents)
        second = builder(documents)
        assert [(chunk.chunk_id, chunk.text) for chunk in first] == [
            (chunk.chunk_id, chunk.text) for chunk in second
        ]
        assert all(chunk.document_id and chunk.text for chunk in first)

    sample = documents[0]
    for section in sample.sections:
        windows = [chunk for chunk in fixed_chunks([sample]) if chunk.heading == section.heading]
        section_words = section.text.split()
        assert windows[0].text.split()[:3] == section_words[:3]
        assert windows[-1].text.split()[-3:] == section_words[-3:]


def test_hashing_embedding_is_deterministic_and_normalised():
    first = embed("supplier delay revised arrival date")
    second = embed("supplier delay revised arrival date")
    assert first.shape == (EMBEDDING_DIM,)
    assert np.array_equal(first, second)
    assert abs(float(np.linalg.norm(first)) - 1.0) < 1e-5
    assert not np.array_equal(first, embed("cash buffer credit limit"))
    assert not embed("the of and").any()


def test_hybrid_strategies_are_deterministic_and_cite_sections():
    index = ChunkIndex.from_documents(load_documents(), "section")
    query = "Can we promise the retailer a revised delivery date before the supplier confirms it?"
    for strategy in ("bm25", "bm25_rerank", "dense", "hybrid", "hybrid_rerank"):
        first = index.search(query, top_k=3, strategy=strategy)
        second = index.search(query, top_k=3, strategy=strategy)
        assert first == second, strategy
        assert first, strategy
        for hit in first:
            assert hit["quote"]
            assert hit["section_id"].startswith(hit["document_id"] + "::")
            assert hit["licence"]


def _chunk(document_id: str, text: str, heading: str = "Rules") -> Chunk:
    return Chunk(
        chunk_id=f"{document_id}::section::0",
        document_id=document_id,
        title=document_id,
        heading=heading,
        text=text,
        doc_type="policy",
        version="1.0",
        effective_from="2026-01-01",
        status="approved",
        licence="CC0-1.0 (test)",
        source_url="",
        retrieved_on="",
        parties="all",
        classification="synthetic",
        path=f"{document_id}.md",
    )


def test_rerank_flips_a_token_stuffed_first_stage_winner():
    covering = _chunk(
        "DOC-COVER",
        "The minimum cash buffer excludes a candidate plan when projected ending cash falls below the threshold.",
    )
    repetitive = _chunk("DOC-REPEAT", "cash " * 40)
    query = "minimum cash buffer candidate plan projected ending cash"
    reranked = ChunkIndex._rerank(
        _tokens(query),
        [(repetitive, 1.0), (covering, 0.3)],
        {"DOC-COVER": 0.7, "DOC-REPEAT": 0.2},
    )
    scores = {chunk.document_id: score for chunk, score in reranked}
    assert reranked[0][0].document_id == "DOC-COVER"
    assert scores["DOC-COVER"] > scores["DOC-REPEAT"]


def test_paragraph_chunking_keeps_expanded_recall():
    documents = load_documents(DEFAULT_CORPUS_DIR, extra_roots=[TRACK_B_CORPUS_DIR])
    index = ChunkIndex.from_documents(documents, "paragraph")
    result = evaluate(_Bm25View(index), GOLDEN)
    assert result["recall_at_3"] >= 0.90, result["misses"]
    assert result["recall_at_5"] >= 0.90, result["misses"]


class _Bm25View:
    def __init__(self, index: ChunkIndex):
        self._index = index

    def search(self, query: str, top_k: int = 5, **kwargs):
        return self._index.search(query, top_k=top_k, strategy="bm25", **kwargs)
