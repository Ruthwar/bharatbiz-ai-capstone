"""Load the approved reference corpus.

Only Markdown files with frontmatter in `data/knowledge_docs/` are indexed. Inbound
messages, retailer records and pilot data are never part of this corpus (POL-DAT-004).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CORPUS_DIR = PROJECT_ROOT / "data" / "knowledge_docs"
TRACK_B_CORPUS_DIR = PROJECT_ROOT / "data" / "knowledge_docs_track_b"

REQUIRED_FIELDS = (
    "document_id",
    "title",
    "doc_type",
    "version",
    "status",
    "effective_from",
    "owner",
    "classification",
    "licence",
)
DOC_TYPES = ("policy", "sop", "supplier_terms", "case_note", "regulation")
CLASSIFICATIONS = ("synthetic", "public_regulation")

_HEADING = re.compile(r"^##\s+(?P<heading>.+?)\s*$", re.MULTILINE)
_H1 = re.compile(r"^#\s+.+?$", re.MULTILINE)


class CorpusError(ValueError):
    """The corpus cannot be indexed safely."""


@dataclass(frozen=True)
class Section:
    section_id: str
    document_id: str
    heading: str
    text: str


@dataclass(frozen=True)
class Document:
    document_id: str
    title: str
    doc_type: str
    version: str
    status: str
    effective_from: str
    owner: str
    classification: str
    licence: str
    parties: tuple[str, ...] = ()
    skus: tuple[str, ...] = ()
    source_url: str = ""
    retrieved_on: str = ""
    path: str = ""
    sections: tuple[Section, ...] = field(default_factory=tuple)


def _split_list(value: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in value.split(",") if part.strip())


def _parse_frontmatter(text: str, path: Path) -> tuple[dict[str, str], str]:
    if not text.startswith("---"):
        raise CorpusError(f"{path.name}: missing frontmatter")
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise CorpusError(f"{path.name}: unterminated frontmatter")
    meta: dict[str, str] = {}
    for line in parts[1].strip().splitlines():
        if not line.strip():
            continue
        key, sep, value = line.partition(":")
        if not sep:
            raise CorpusError(f"{path.name}: malformed frontmatter line {line!r}")
        meta[key.strip()] = value.strip().strip('"')
    return meta, parts[2]


def _split_sections(document_id: str, body: str) -> tuple[Section, ...]:
    body = _H1.sub("", body, count=1).strip()
    matches = list(_HEADING.finditer(body))
    sections: list[Section] = []
    preamble = body[: matches[0].start()].strip() if matches else body
    if preamble:
        sections.append(Section(f"{document_id}#0", document_id, "", preamble))
    for index, match in enumerate(matches, start=1):
        end = matches[index].start() if index < len(matches) else len(body)
        text = body[match.end() : end].strip()
        if text:
            sections.append(Section(f"{document_id}#{index}", document_id, match.group("heading"), text))
    if not sections:
        raise CorpusError(f"{document_id}: no indexable text")
    return tuple(sections)


def parse_document(path: Path) -> Document:
    meta, body = _parse_frontmatter(path.read_text(encoding="utf-8"), path)
    missing = [name for name in REQUIRED_FIELDS if not meta.get(name)]
    if missing:
        raise CorpusError(f"{path.name}: missing {', '.join(missing)}")
    if meta["doc_type"] not in DOC_TYPES:
        raise CorpusError(f"{path.name}: unknown doc_type {meta['doc_type']!r}")
    if meta["classification"] not in CLASSIFICATIONS:
        raise CorpusError(f"{path.name}: unknown classification {meta['classification']!r}")
    try:
        date.fromisoformat(meta["effective_from"])
    except ValueError as exc:
        raise CorpusError(f"{path.name}: effective_from is not a date") from exc

    source_url = meta.get("source_url", "")
    retrieved_on = meta.get("retrieved_on", "")
    if source_url.lower() == "none":
        source_url = ""
    if retrieved_on.lower() == "none":
        retrieved_on = ""
    if meta["classification"] == "public_regulation":
        if not source_url or not retrieved_on:
            raise CorpusError(f"{path.name}: regulatory extracts need source_url and retrieved_on")
        try:
            date.fromisoformat(retrieved_on)
        except ValueError as exc:
            raise CorpusError(f"{path.name}: retrieved_on is not a date") from exc

    document_id = meta["document_id"]
    return Document(
        document_id=document_id,
        title=meta["title"],
        doc_type=meta["doc_type"],
        version=meta["version"],
        status=meta["status"],
        effective_from=meta["effective_from"],
        owner=meta["owner"],
        classification=meta["classification"],
        licence=meta["licence"],
        parties=_split_list(meta.get("parties", "")),
        skus=_split_list(meta.get("skus", "")),
        source_url=source_url,
        retrieved_on=retrieved_on,
        path=path.name,
        sections=_split_sections(document_id, body),
    )


def corpus_files(corpus_dir: Path, extra_roots: Iterable[Path] | None = None) -> list[Path]:
    """All Markdown files across the base corpus and any additive experiment roots."""
    roots = [Path(corpus_dir)]
    roots.extend(Path(root) for root in extra_roots or ())
    paths: list[Path] = []
    for root in roots:
        if not root.is_dir():
            raise CorpusError(f"Corpus directory not found: {root}")
        paths.extend(sorted(root.glob("*.md")))
    if not paths:
        raise CorpusError(f"No documents in {', '.join(str(root) for root in roots)}")
    return paths


def load_documents(root: Path | None = None, extra_roots: Iterable[Path] | None = None) -> list[Document]:
    """Parse the base corpus and optionally any additive corpus roots.

    With no arguments this reads only `data/knowledge_docs/`, so the runtime citation
    corpus stays exactly the curated 33 documents.
    """
    corpus_dir = Path(root) if root else DEFAULT_CORPUS_DIR
    documents = [parse_document(path) for path in corpus_files(corpus_dir, extra_roots)]
    seen: set[str] = set()
    for document in documents:
        if document.document_id in seen:
            raise CorpusError(f"Duplicate document_id {document.document_id}")
        seen.add(document.document_id)
    return documents
