"""Chunking, lexical-hashing embeddings, hybrid fusion and reranking.

This module is the measured upgrade path for retrieval. It is deliberately local and
deterministic: SQLite FTS5 BM25 plus a character n-gram hashing embedding implemented with
numpy. There is no sentence-transformer, no network call and no model download, so the same
corpus and query always produce the same ranking.

The embedding is lexical, not semantic. It is reported as "hashing embeddings" in every
result so the comparison is not overstated.
"""

from __future__ import annotations

import hashlib
import math
import re
import sqlite3
from collections import Counter
from dataclasses import dataclass
from datetime import date
from typing import Iterable, Sequence

import numpy as np

from app.rag.corpus import Document
from app.rag.retrieval import _STOPWORDS, _tokens, best_quote, party_allows

EMBEDDING_DIM = 512
EMBEDDING_NAME = "deterministic char/word hashing (blake2b, 512d, no model)"
STRATEGIES = ("bm25", "bm25_rerank", "dense", "hybrid", "hybrid_rerank")
CHUNK_STRATEGIES = ("section", "paragraph", "fixed")

_CHUNK_COLUMNS = (
    "chunk_id", "document_id", "heading", "body", "title", "doc_type", "version",
    "effective_from", "status", "licence", "source_url", "retrieved_on", "parties",
    "classification", "path",
)
_CHUNK_WEIGHTS = {"heading": 4.0, "body": 1.0, "title": 2.0}
_WORD = re.compile(r"[a-z0-9\u0900-\u097f]+")


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    document_id: str
    title: str
    heading: str
    text: str
    doc_type: str
    version: str
    effective_from: str
    status: str
    licence: str
    source_url: str
    retrieved_on: str
    parties: str
    classification: str
    path: str


def _make_chunk(document: Document, heading: str, text: str, index: int, strategy: str) -> Chunk:
    return Chunk(
        chunk_id=f"{document.document_id}::{strategy}::{index}",
        document_id=document.document_id,
        title=document.title,
        heading=heading,
        text=text,
        doc_type=document.doc_type,
        version=document.version,
        effective_from=document.effective_from,
        status=document.status,
        licence=document.licence,
        source_url=document.source_url,
        retrieved_on=document.retrieved_on,
        parties=", ".join(document.parties),
        classification=document.classification,
        path=document.path,
    )


def _chunk_from_section(document: Document, section, index: int, strategy: str) -> Chunk:
    return _make_chunk(document, section.heading, section.text, index, strategy)


def _windows(words: Sequence[str], size: int, overlap: int) -> list[list[str]]:
    if size < 1:
        raise ValueError("window size must be positive")
    step = max(1, size - overlap)
    windows = [list(words[start : start + size]) for start in range(0, len(words), step)]
    return [window for window in windows if window]


def section_chunks(documents: Iterable[Document]) -> list[Chunk]:
    chunks: list[Chunk] = []
    for document in documents:
        for section in document.sections:
            chunks.append(_chunk_from_section(document, section, len(chunks), "section"))
    return chunks


def paragraph_chunks(documents: Iterable[Document], max_words: int = 180) -> list[Chunk]:
    """Pack paragraphs into chunks up to `max_words`, keeping headings with their text."""
    chunks: list[Chunk] = []
    for document in documents:
        buffer: list[str] = []
        heading = ""
        count = 0
        for section in document.sections:
            paragraphs = [part.strip() for part in re.split(r"\n\s*\n", section.text) if part.strip()]
            for paragraph in paragraphs:
                words = len(paragraph.split())
                if buffer and count + words > max_words:
                    chunks.append(
                        _make_chunk(document, heading or section.heading, "\n\n".join(buffer), len(chunks), "paragraph")
                    )
                    buffer, count = [], 0
                if not buffer:
                    heading = section.heading
                buffer.append(paragraph)
                count += words
        if buffer:
            chunks.append(_make_chunk(document, heading, "\n\n".join(buffer), len(chunks), "paragraph"))
    return chunks


def fixed_chunks(documents: Iterable[Document], size: int = 160, overlap: int = 40) -> list[Chunk]:
    """Ignore section boundaries and cut fixed word windows with overlap."""
    chunks: list[Chunk] = []
    for document in documents:
        for section in document.sections:
            words = section.text.split()
            for window in _windows(words, size, overlap):
                chunks.append(_make_chunk(document, section.heading, " ".join(window), len(chunks), "fixed"))
    return chunks


def build_chunks(documents: Iterable[Document], strategy: str) -> list[Chunk]:
    documents = list(documents)
    if strategy == "section":
        return section_chunks(documents)
    if strategy == "paragraph":
        return paragraph_chunks(documents)
    if strategy == "fixed":
        return fixed_chunks(documents)
    raise ValueError(f"unknown chunk strategy {strategy!r}")


def _features(text: str) -> Counter[str]:
    words = [word for word in _WORD.findall(text.lower()) if len(word) >= 2 and word not in _STOPWORDS]
    features: Counter[str] = Counter()
    for word in words:
        features[f"w:{word}"] += 1
        if len(word) >= 3:
            padded = f"^{word}$"
            for size in (3, 4):
                for position in range(len(padded) - size + 1):
                    features[f"c:{padded[position:position + size]}"] += 1
    return features


def _hash_bucket(feature: str) -> tuple[int, float]:
    digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
    value = int.from_bytes(digest, "big")
    return value % EMBEDDING_DIM, 1.0 if (value >> 63) & 1 == 0 else -1.0


def embed(text: str) -> np.ndarray:
    vector = np.zeros(EMBEDDING_DIM, dtype=np.float32)
    for feature, count in _features(text).items():
        index, sign = _hash_bucket(feature)
        vector[index] += sign * (1.0 + math.log(count))
    norm = float(np.linalg.norm(vector))
    return vector / norm if norm else vector


def embed_many(texts: Sequence[str]) -> np.ndarray:
    if not texts:
        return np.zeros((0, EMBEDDING_DIM), dtype=np.float32)
    matrix = np.vstack([embed(text) for text in texts])
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0.0] = 1.0
    return matrix / norms


class ChunkIndex:
    """An in-memory FTS5 + embedding index over one chunking strategy."""

    def __init__(self, chunks: Sequence[Chunk], strategy: str):
        self.strategy = strategy
        self.chunks = list(chunks)
        self._conn: sqlite3.Connection | None = None
        self._vectors: np.ndarray | None = None

    @classmethod
    def from_documents(
        cls,
        documents: Iterable[Document],
        chunk_strategy: str = "section",
    ) -> "ChunkIndex":
        return cls(build_chunks(documents, chunk_strategy), chunk_strategy)

    # -- FTS -------------------------------------------------------------
    def _connect(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(":memory:", check_same_thread=False)
            self._build()
        return self._conn

    def _build(self) -> None:
        assert self._conn is not None
        self._conn.execute(
            "CREATE VIRTUAL TABLE chunks USING fts5("
            + ", ".join(
                f"{name} UNINDEXED" if name not in ("heading", "body", "title") else name
                for name in _CHUNK_COLUMNS
            )
            + ", tokenize='porter unicode61')"
        )
        for chunk in self.chunks:
            self._conn.execute(
                f"INSERT INTO chunks ({', '.join(_CHUNK_COLUMNS)}) VALUES ({', '.join('?' * len(_CHUNK_COLUMNS))})",
                (
                    chunk.chunk_id, chunk.document_id, chunk.heading, chunk.text, chunk.title,
                    chunk.doc_type, chunk.version, chunk.effective_from, chunk.status,
                    chunk.licence, chunk.source_url, chunk.retrieved_on, chunk.parties,
                    chunk.classification, chunk.path,
                ),
            )
        self._conn.commit()

    def _bm25_rows(self, tokens: Sequence[str], limit: int) -> list[tuple[Chunk, float]]:
        conn = self._connect()
        weights = ", ".join(str(_CHUNK_WEIGHTS.get(column, 0.0)) for column in _CHUNK_COLUMNS)
        expression = " OR ".join(f'"{token}"' for token in tokens)
        rows = conn.execute(
            f"SELECT {', '.join(_CHUNK_COLUMNS)}, bm25(chunks, {weights}) AS score "
            "FROM chunks WHERE chunks MATCH ? ORDER BY score LIMIT ?",
            (expression, limit),
        ).fetchall()
        by_chunk = {chunk.chunk_id: chunk for chunk in self.chunks}
        return [(by_chunk[row[0]], -float(row[-1])) for row in rows if row[0] in by_chunk]

    # -- Embeddings ------------------------------------------------------
    def vectors(self) -> np.ndarray:
        if self._vectors is None:
            self._vectors = embed_many([f"{chunk.title} {chunk.heading} {chunk.text}" for chunk in self.chunks])
        return self._vectors

    def _dense_ranked(self, query: str, limit: int) -> list[tuple[Chunk, float]]:
        vectors = self.vectors()
        if not len(vectors):
            return []
        scores = vectors @ embed(query)
        order = np.argsort(-scores, kind="stable")
        chosen: list[tuple[Chunk, float]] = []
        seen: set[str] = set()
        for position in order:
            chunk = self.chunks[int(position)]
            if chunk.document_id in seen:
                continue
            seen.add(chunk.document_id)
            chosen.append((chunk, float(scores[int(position)])))
            if len(chosen) >= limit:
                break
        return chosen

    # -- Filters ---------------------------------------------------------
    @staticmethod
    def _allowed(
        chunk: Chunk,
        *,
        doc_types: set[str] | None,
        supplier_id: str | None,
        as_of: date | None,
    ) -> bool:
        if doc_types and chunk.doc_type not in doc_types:
            return False
        if not party_allows(chunk.parties, supplier_id):
            return False
        if as_of and chunk.effective_from > as_of.isoformat():
            return False
        return True

    def _best_per_document(
        self,
        ranked: Sequence[tuple[Chunk, float]],
        *,
        limit: int,
        doc_types: set[str] | None,
        supplier_id: str | None,
        as_of: date | None,
    ) -> list[tuple[Chunk, float]]:
        chosen: list[tuple[Chunk, float]] = []
        seen: set[str] = set()
        for chunk, score in ranked:
            if chunk.document_id in seen:
                continue
            if not self._allowed(chunk, doc_types=doc_types, supplier_id=supplier_id, as_of=as_of):
                continue
            seen.add(chunk.document_id)
            chosen.append((chunk, score))
            if len(chosen) >= limit:
                break
        return chosen

    # -- Fusion ----------------------------------------------------------
    @staticmethod
    def _reciprocal_rank(
        lexical: Sequence[tuple[Chunk, float]],
        dense: Sequence[tuple[Chunk, float]],
        k: int = 60,
    ) -> list[tuple[Chunk, float]]:
        scores: dict[str, float] = {}
        chunks: dict[str, Chunk] = {}
        for ranked in (lexical, dense):
            for rank, (chunk, _score) in enumerate(ranked, start=1):
                chunks.setdefault(chunk.document_id, chunk)
                scores[chunk.document_id] = scores.get(chunk.document_id, 0.0) + 1.0 / (k + rank)
        ordered = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
        return [(chunks[document_id], score) for document_id, score in ordered]

    @staticmethod
    def _rerank(
        query_tokens: Sequence[str],
        candidates: Sequence[tuple[Chunk, float]],
        dense: dict[str, float],
    ) -> list[tuple[Chunk, float]]:
        if not candidates:
            return []
        max_fusion = max(score for _chunk, score in candidates) or 1.0
        bigrams = {
            (query_tokens[index], query_tokens[index + 1])
            for index in range(len(query_tokens) - 1)
        }
        reranked: list[tuple[Chunk, float]] = []
        for chunk, fusion in candidates:
            haystack = f"{chunk.title} {chunk.heading} {chunk.text}".lower()
            heading = f"{chunk.title} {chunk.heading}".lower()
            coverage = sum(1 for token in query_tokens if token in haystack) / len(query_tokens)
            heading_coverage = sum(1 for token in query_tokens if token in heading) / len(query_tokens)
            bigram_coverage = (
                sum(1 for left, right in bigrams if f"{left} {right}" in haystack) / len(bigrams)
                if bigrams
                else 0.0
            )
            cosine = max(0.0, dense.get(chunk.document_id, 0.0))
            score = (
                0.35 * coverage
                + 0.15 * heading_coverage
                + 0.10 * bigram_coverage
                + 0.25 * cosine
                + 0.15 * (fusion / max_fusion)
            )
            reranked.append((chunk, score))
        reranked.sort(key=lambda item: (-item[1], item[0].document_id))
        return reranked

    # -- Public API ------------------------------------------------------
    def search(
        self,
        query: str,
        top_k: int = 5,
        doc_types: Iterable[str] | None = None,
        supplier_id: str | None = None,
        as_of: date | None = None,
        strategy: str = "hybrid_rerank",
    ) -> list[dict]:
        tokens = _tokens(query)
        if not tokens or top_k < 1:
            return []
        if strategy not in STRATEGIES:
            raise ValueError(f"unknown retrieval strategy {strategy!r}")
        wanted = {value for value in doc_types} if doc_types else None
        fetch = max(top_k * 12, 60)

        lexical: list[tuple[Chunk, float]] = []
        if strategy in {"bm25", "bm25_rerank", "hybrid", "hybrid_rerank"}:
            lexical = self._best_per_document(
                self._bm25_rows(tokens, fetch),
                limit=max(top_k * 4, 40),
                doc_types=wanted,
                supplier_id=supplier_id,
                as_of=as_of,
            )
        dense: list[tuple[Chunk, float]] = []
        if strategy in {"bm25_rerank", "dense", "hybrid", "hybrid_rerank"}:
            dense = self._best_per_document(
                self._dense_ranked(query, fetch),
                limit=max(top_k * 4, 40),
                doc_types=wanted,
                supplier_id=supplier_id,
                as_of=as_of,
            )

        if strategy == "bm25":
            ranked = lexical
        elif strategy == "dense":
            ranked = dense
        elif strategy == "bm25_rerank":
            dense_scores = {chunk.document_id: score for chunk, score in dense}
            ranked = self._rerank(tokens, lexical[: max(top_k * 4, 20)], dense_scores)
        elif strategy == "hybrid":
            ranked = self._reciprocal_rank(lexical, dense)
        else:
            fused = self._reciprocal_rank(lexical, dense)
            dense_scores = {chunk.document_id: score for chunk, score in dense}
            ranked = self._rerank(tokens, fused[: max(top_k * 4, 20)], dense_scores)

        results: list[dict] = []
        for chunk, score in ranked[:top_k]:
            results.append(
                {
                    "section_id": chunk.chunk_id,
                    "document_id": chunk.document_id,
                    "title": chunk.title,
                    "heading": chunk.heading,
                    "text": chunk.text,
                    "quote": best_quote(chunk.text, tokens),
                    "doc_type": chunk.doc_type,
                    "version": chunk.version,
                    "effective_from": chunk.effective_from,
                    "classification": chunk.classification,
                    "licence": chunk.licence,
                    "source_url": chunk.source_url or None,
                    "retrieved_on": chunk.retrieved_on or None,
                    "score": round(score, 6),
                }
            )
        return results
