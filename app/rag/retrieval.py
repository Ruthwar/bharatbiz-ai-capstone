"""Deterministic lexical retrieval over the approved corpus.

SQLite FTS5 with BM25 ranking. No embeddings, no network, no model: the same corpus and
the same query always produce the same sections in the same order. Retrieved text is a
citation, never an input to arithmetic (POL-DAT-004 R10).
"""

from __future__ import annotations

import hashlib
import os
import re
import sqlite3
import time
from datetime import date
from pathlib import Path
from typing import Iterable, Sequence

from app.observability import record_retrieval
from app.rag.corpus import DEFAULT_CORPUS_DIR, Document, corpus_files, load_documents

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INDEX_PATH = PROJECT_ROOT / "data" / "runtime" / "rag.sqlite3"
SCHEMA_VERSION = "1"

_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "been", "before", "but", "by", "can", "could",
    "do", "does", "for", "from", "had", "has", "have", "how", "if", "in", "into", "is", "it",
    "its", "may", "must", "not", "of", "on", "or", "our", "shall", "should", "that", "the",
    "their", "then", "there", "these", "they", "this", "to", "was", "we", "were", "what",
    "when", "where", "which", "who", "why", "will", "with", "would", "you", "your",
}

_COLUMNS = (
    "section_id", "document_id", "heading", "body", "title", "doc_type", "version",
    "effective_from", "status", "licence", "source_url", "retrieved_on", "parties",
    "classification", "path",
)
_WEIGHTS = {"heading": 4.0, "body": 1.0, "title": 2.0}


def _tokens(query: str) -> list[str]:
    words = re.findall(r"[a-z0-9\u0900-\u097f]+", query.lower())
    seen: list[str] = []
    for word in words:
        if len(word) < 2 or word in _STOPWORDS or word in seen:
            continue
        seen.append(word)
        if len(seen) == 12:
            break
    return seen


def _match_expression(tokens: Sequence[str]) -> str:
    return " OR ".join(f'"{token}"' for token in tokens)


_SENTENCE = re.compile(r"(?<=[.!?])\s+")


def party_allows(parties: str, supplier_id: str | None) -> bool:
    """Party metadata uses comma-separated ids; "all" and "RET-all" apply universally to the decision."""
    if not supplier_id:
        return True
    declared = {part.strip() for part in parties.split(",") if part.strip()}
    return bool(declared & {"all", "RET-all"}) or supplier_id in declared


def best_quote(text: str, tokens: Sequence[str], limit: int = 320) -> str:
    """Pick the sentence that covers the most query terms, so the card quotes rather than summarises."""
    sentences = [sentence.strip() for sentence in _SENTENCE.split(text) if sentence.strip()]
    if not sentences:
        return ""
    scored = []
    for index, sentence in enumerate(sentences):
        lowered = sentence.lower()
        coverage = sum(1 for token in tokens if token in lowered)
        scored.append((coverage, -index, sentence))
    scored.sort(reverse=True)
    best = scored[0][2]
    if len(best) > limit:
        best = best[:limit].rsplit(" ", 1)[0] + "…"
    return best


def _fingerprint(paths: Sequence[Path]) -> str:
    """Hash file content, not timestamps, so copied or re-checked-out corpora reuse the index."""
    digest = hashlib.sha256()
    for path in paths:
        digest.update(f"{path.name}:".encode())
        digest.update(hashlib.sha256(path.read_bytes()).digest())
        digest.update(b"\n")
    return digest.hexdigest()


def corpus_fingerprint(corpus_dir: Path | None = None, extra_roots: Iterable[Path] | None = None) -> str:
    """Stable content hash for a base corpus plus optional additive roots."""
    base = Path(corpus_dir) if corpus_dir else DEFAULT_CORPUS_DIR
    return _fingerprint(corpus_files(base, extra_roots))


class RagIndex:
    """One FTS5 index over the Markdown corpus, rebuilt when the corpus changes."""

    def __init__(
        self,
        index_path: str | Path = DEFAULT_INDEX_PATH,
        corpus_dir: Path | None = None,
        extra_corpus_dirs: Iterable[Path] | None = None,
    ):
        self.index_path = str(index_path)
        self.corpus_dir = Path(corpus_dir) if corpus_dir else DEFAULT_CORPUS_DIR
        self.extra_corpus_dirs = [Path(root) for root in extra_corpus_dirs or ()]
        self._fingerprint: str | None = None
        self._memory: sqlite3.Connection | None = None

    def _connect(self) -> sqlite3.Connection:
        if self.index_path == ":memory:":
            if self._memory is None:
                # Streamlit and the FastAPI test client may call from another thread.
                self._memory = sqlite3.connect(":memory:", check_same_thread=False)
            return self._memory
        Path(self.index_path).parent.mkdir(parents=True, exist_ok=True)
        return sqlite3.connect(self.index_path)

    def _release(self, conn: sqlite3.Connection) -> None:
        if self.index_path != ":memory:":
            conn.close()

    def ensure(self) -> None:
        fingerprint = corpus_fingerprint(self.corpus_dir, self.extra_corpus_dirs)
        if fingerprint == self._fingerprint:
            return
        conn = self._connect()
        try:
            if self._meta(conn, "fingerprint") != fingerprint or self._meta(conn, "schema") != SCHEMA_VERSION:
                self._build(conn, fingerprint)
                conn.commit()
        finally:
            self._release(conn)
        self._fingerprint = fingerprint

    def _meta(self, conn: sqlite3.Connection, key: str) -> str | None:
        try:
            row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        except sqlite3.OperationalError:
            return None
        return row[0] if row else None

    def _build(self, conn: sqlite3.Connection, fingerprint: str) -> None:
        documents = load_documents(self.corpus_dir, extra_roots=self.extra_corpus_dirs)
        conn.execute("DROP TABLE IF EXISTS sections")
        conn.execute("DROP TABLE IF EXISTS meta")
        conn.execute(
            "CREATE VIRTUAL TABLE sections USING fts5("
            + ", ".join(f"{name} UNINDEXED" if name not in ("heading", "body", "title") else name
                        for name in _COLUMNS)
            + ", tokenize='porter unicode61')"
        )
        conn.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        for document in documents:
            for section in document.sections:
                conn.execute(
                    f"INSERT INTO sections ({', '.join(_COLUMNS)}) VALUES ({', '.join('?' * len(_COLUMNS))})",
                    (
                        section.section_id, document.document_id, section.heading, section.text,
                        document.title, document.doc_type, document.version, document.effective_from,
                        document.status, document.licence, document.source_url, document.retrieved_on,
                        ", ".join(document.parties), document.classification, document.path,
                    ),
                )
        conn.execute("INSERT INTO meta VALUES ('fingerprint', ?)", (fingerprint,))
        conn.execute("INSERT INTO meta VALUES ('schema', ?)", (SCHEMA_VERSION,))

    def documents(self) -> list[Document]:
        return load_documents(self.corpus_dir, extra_roots=self.extra_corpus_dirs)

    def document_meta(self, document_id: str) -> dict | None:
        """Frontmatter metadata for one approved document, read from the current index."""
        self.ensure()
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT document_id, title, doc_type, version, effective_from, status, licence, "
                "source_url, retrieved_on, parties, classification "
                "FROM sections WHERE document_id = ? LIMIT 1",
                (document_id,),
            ).fetchone()
        finally:
            self._release(conn)
        if row is None:
            return None
        keys = (
            "document_id", "title", "doc_type", "version", "effective_from", "status",
            "licence", "source_url", "retrieved_on", "parties", "classification",
        )
        return dict(zip(keys, row))

    def document_section(self, document_id: str, limit: int = 320) -> dict | None:
        """One representative section for a mandatory document that BM25 did not surface."""
        self.ensure()
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT section_id, heading, body, title, doc_type, version, effective_from, status, "
                "licence, source_url, retrieved_on, parties, classification "
                "FROM sections WHERE document_id = ?",
                (document_id,),
            ).fetchall()
        finally:
            self._release(conn)
        if not rows:
            return None
        keys = (
            "section_id", "heading", "text", "title", "doc_type", "version", "effective_from",
            "status", "licence", "source_url", "retrieved_on", "parties", "classification",
        )
        records = [dict(zip(keys, row)) for row in rows]

        def rank(record: dict) -> int:
            heading = (record["heading"] or "").lower()
            if heading == "rules":
                return 0
            return 1 if "rule" in heading else 2

        record = sorted(records, key=rank)[0]
        text = record.pop("text")
        quote = text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0] + "…"
        return {
            **record,
            "document_id": document_id,
            "text": text,
            "quote": quote,
            "source_url": record["source_url"] or None,
            "retrieved_on": record["retrieved_on"] or None,
            "score": 0.0,
        }

    def search(
        self,
        query: str,
        top_k: int = 5,
        doc_types: Iterable[str] | None = None,
        supplier_id: str | None = None,
        as_of: date | None = None,
    ) -> list[dict]:
        tokens = _tokens(query)
        if not tokens or top_k < 1:
            return []
        self.ensure()
        # A short section can outrank the right one on one incidental word. Require the section to
        # cover a share of the question, not just a token of it.
        min_coverage = max(1, min(5, -(-len(tokens) * 35 // 100)))
        wanted = {value for value in doc_types} if doc_types else None
        weights = ", ".join(str(_WEIGHTS.get(column, 0.0)) for column in _COLUMNS)
        conn = self._connect()
        try:
            rows = conn.execute(
                f"SELECT {', '.join(_COLUMNS)}, bm25(sections, {weights}) AS score "
                "FROM sections WHERE sections MATCH ? ORDER BY score LIMIT ?",
                (_match_expression(tokens), max(top_k * 12, 60)),
            ).fetchall()
        finally:
            self._release(conn)

        results: list[dict] = []
        seen_documents: set[str] = set()
        for row in rows:
            record = dict(zip(_COLUMNS, row))
            document_id = record["document_id"]
            if document_id in seen_documents:
                continue
            haystack = f"{record['title']} {record['heading']} {record['body']}".lower()
            if sum(1 for token in tokens if token in haystack) < min_coverage:
                continue
            if wanted and record["doc_type"] not in wanted:
                continue
            if not party_allows(record["parties"], supplier_id):
                continue
            if as_of and record["effective_from"] > as_of.isoformat():
                continue
            seen_documents.add(document_id)
            results.append(
                {
                    "section_id": record["section_id"],
                    "document_id": document_id,
                    "title": record["title"],
                    "heading": record["heading"],
                    "text": record["body"],
                    "quote": best_quote(record["body"], tokens),
                    "doc_type": record["doc_type"],
                    "version": record["version"],
                    "effective_from": record["effective_from"],
                    "classification": record["classification"],
                    "licence": record["licence"],
                    "source_url": record["source_url"] or None,
                    "retrieved_on": record["retrieved_on"] or None,
                    "score": round(-row[-1], 4),
                }
            )
            if len(results) == top_k:
                break
        return results


_INDEX: RagIndex | None = None
_INDEX_KEY: tuple[str, tuple[str, ...]] | None = None


def _configured_extra_roots() -> list[Path]:
    """Optional additive corpora, separated by os.pathsep. Empty by default."""
    raw = os.getenv("BHARATBIZ_RAG_CORPUS", "").strip()
    return [Path(part) for part in raw.split(os.pathsep) if part.strip()]


def get_index() -> RagIndex:
    global _INDEX, _INDEX_KEY
    path = os.getenv("BHARATBIZ_RAG_DB") or DEFAULT_INDEX_PATH
    roots = _configured_extra_roots()
    key = (path, tuple(str(root) for root in roots))
    if _INDEX is None or _INDEX_KEY != key:
        _INDEX = RagIndex(path, extra_corpus_dirs=roots)
        _INDEX_KEY = key
    return _INDEX


_HYBRID_INDEX = None
_HYBRID_KEY: tuple[str, tuple[str, ...]] | None = None


def get_hybrid_index():
    """Expanded-corpus chunk index used only when a hybrid strategy is explicitly selected."""
    global _HYBRID_INDEX, _HYBRID_KEY
    from app.rag.hybrid import CHUNK_STRATEGIES, ChunkIndex

    roots = _configured_extra_roots()
    chunking = (os.getenv("BHARATBIZ_RAG_CHUNKS") or "section").strip().lower()
    if chunking not in CHUNK_STRATEGIES:
        chunking = "section"
    key = (chunking, tuple(str(root) for root in roots))
    if _HYBRID_INDEX is None or _HYBRID_KEY != key:
        documents = load_documents(DEFAULT_CORPUS_DIR, extra_roots=roots)
        _HYBRID_INDEX = ChunkIndex.from_documents(documents, chunking)
        _HYBRID_KEY = key
    return _HYBRID_INDEX


def reset_index() -> None:
    """Drop the cached singletons so tests can change corpus configuration."""
    global _INDEX, _INDEX_KEY, _HYBRID_INDEX, _HYBRID_KEY
    _INDEX = None
    _INDEX_KEY = None
    _HYBRID_INDEX = None
    _HYBRID_KEY = None


def retrieve(
    query: str,
    top_k: int = 5,
    doc_types: Iterable[str] | None = None,
    supplier_id: str | None = None,
    as_of: date | None = None,
) -> list[dict]:
    """Return up to `top_k` sections, best section per document.

    BM25 over the curated corpus is the default. Setting BHARATBIZ_RAG_STRATEGY to
    `dense`, `hybrid` or `hybrid_rerank` selects the measured experimental path instead;
    an unknown value is treated as `bm25`.
    """
    strategy = (os.getenv("BHARATBIZ_RAG_STRATEGY") or "bm25").strip().lower()
    started = time.monotonic()
    if strategy in {"bm25_rerank", "dense", "hybrid", "hybrid_rerank"}:
        results = get_hybrid_index().search(
            query,
            top_k=top_k,
            doc_types=doc_types,
            supplier_id=supplier_id,
            as_of=as_of,
            strategy=strategy,
        )
    else:
        results = get_index().search(
            query, top_k=top_k, doc_types=doc_types, supplier_id=supplier_id, as_of=as_of
        )
    record_retrieval(
        query,
        [row["document_id"] for row in results],
        (time.monotonic() - started) * 1000,
        top_k=top_k,
        hits=len(results),
    )
    return results


def document_meta(document_id: str) -> dict | None:
    return get_index().document_meta(document_id)


def document_section(document_id: str) -> dict | None:
    return get_index().document_section(document_id)
