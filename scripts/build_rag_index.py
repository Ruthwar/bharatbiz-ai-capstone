"""Build the retrieval index and the corpus manifest.

Run after editing anything in data/knowledge_docs: python scripts/build_rag_index.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.rag.corpus import DEFAULT_CORPUS_DIR, load_documents  # noqa: E402
from app.rag.retrieval import DEFAULT_INDEX_PATH, RagIndex  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS_DIR)
    parser.add_argument("--index", type=Path, default=Path(os.getenv("BHARATBIZ_RAG_DB", DEFAULT_INDEX_PATH)))
    parser.add_argument("--manifest", type=Path, default=DEFAULT_CORPUS_DIR / "manifest.json")
    args = parser.parse_args()

    documents = load_documents(args.corpus)
    entries = []
    for document in documents:
        path = args.corpus / document.path
        payload = path.read_bytes()
        entries.append(
            {
                "document_id": document.document_id,
                "title": document.title,
                "doc_type": document.doc_type,
                "version": document.version,
                "effective_from": document.effective_from,
                "classification": document.classification,
                "source_url": document.source_url or None,
                "retrieved_on": document.retrieved_on or None,
                "file": document.path,
                "bytes": len(payload),
                "sections": len(document.sections),
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        )
    manifest = {
        "corpus_version": date.today().isoformat(),
        "document_count": len(entries),
        "section_count": sum(entry["sections"] for entry in entries),
        "total_bytes": sum(entry["bytes"] for entry in entries),
        "documents": entries,
    }
    args.manifest.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    RagIndex(args.index, args.corpus).ensure()
    print(
        f"Indexed {manifest['document_count']} documents / {manifest['section_count']} sections "
        f"({manifest['total_bytes'] / 1024:.1f} KiB) into {args.index}"
    )
    print(f"Manifest: {args.manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
