# Track B retrieval experiments: corpus, chunking, hybrid search and reranking

This note records the measured retrieval work added for the Track B requirements. It is separate
from the canonical RAG evaluation in `docs/RAG_EVALUATION.md`: that document describes the runtime
citation path, while this one describes the offline ablations on an additive corpus.

Nothing here changes the demo's citation corpus. `data/knowledge_docs/` remains the only source of
truth for review-card citations, and the default retrieval path remains SQLite FTS5 BM25 over those
33 documents.

## 1. What was added

| Piece | Location | Purpose |
| --- | --- | --- |
| Additive corpus generator | `scripts/build_track_b_corpus.py` | Writes 480 deterministic synthetic Markdown documents with frontmatter, provenance and hashes |
| Additive corpus | `data/knowledge_docs_track_b/` | Area addenda, category SOPs, supplier-term addenda, case notes, circulars and quick references |
| Multi-root corpus loader | `app/rag/corpus.py` | `load_documents(extra_roots=...)`, default remains the curated 33 documents |
| Multi-corpus index and content fingerprint | `app/rag/retrieval.py` | `RagIndex(extra_corpus_dirs=...)`; fingerprint hashes file bytes, not mtimes |
| Chunking, embeddings, fusion, reranking | `app/rag/hybrid.py` | Section, paragraph and fixed-window chunks; hashing embeddings; RRF; deterministic rerank |
| Ablation runner | `app/evaluation/rag_experiments.py` | Scores every strategy on the same frozen 40 queries |
| CLI | `scripts/eval_rag_experiments.py` | Prints the comparison and writes the full result JSON |
| Tests | `tests/test_track_b_rag.py` | Corpus integrity, loader behaviour, chunking, embeddings, fusion, reranking, runtime defaults |

The generated corpus is subordinate by construction: every document states that the
distributor-wide policy prevails if the two appear to differ. No document claims to be a real
policy, supplier agreement or regulatory extract, and no synthetic document carries a source URL.

## 2. Corpus

| Item | Value |
| --- | --- |
| Runtime corpus | 33 documents, 203 sections, 104.6 KiB |
| Track B additive corpus | 480 documents, 1,920 sections, 732.4 KiB |
| Combined experiment corpus | 513 documents, 2,603 sections, 837.0 KiB |
| Generator seed | `20261124` |
| Composition | 40 area addenda, 60 category SOPs, 40 supplier-term addenda, 120 case notes, 110 circulars, 110 quick references |
| Classification | `synthetic` |
| Integrity | Per-document SHA-256 and combined manifest in `data/knowledge_docs_track_b/manifest.json` |

The generator supports `--check`, and `tests/test_track_b_rag.py` fails if the committed corpus
drifts from the generator output. The canonical manifest and golden queries were not edited.

## 3. Methods

All strategies use the same frozen queries (`data/eval/golden_queries.json`, SHA-256
`cb1ae816356f…`), the same top-5 cut-off and the same metric definitions used by
`scripts/eval_rag.py`.

| Channel | Implementation |
| --- | --- |
| BM25 | SQLite FTS5, porter + unicode61, heading/body/title weights 4/1/2, best chunk per document, 35% query coverage floor |
| Dense | Deterministic hashing embedding: word unigrams plus character 3–4 grams, blake2b signed hashing into 512 dimensions, sublinear term frequency, L2 normalised, cosine via dot product |
| Hybrid | Reciprocal rank fusion of BM25 and dense document rankings, `k = 60` |
| Rerank | First-stage candidates rescored with 0.35 query coverage + 0.15 heading coverage + 0.10 bigram coverage + 0.25 dense cosine + 0.15 fusion, deterministic tie-break by document id |

The embedding is lexical, not semantic. It is implemented with numpy only because no sentence
model is available in this environment; it is reported as hashing embeddings everywhere so the
result is not mistaken for a neural retriever.

Chunking strategies:

- **section** — one chunk per frontmatter-governed section, matching the runtime index.
- **paragraph** — paragraphs packed up to 180 words, merging short sections.
- **fixed** — 160-word windows with 40-word overlap inside each section.

## 4. Measured results

Measured 2026-11-24 on a local run. Latency is hardware-dependent and is shown for shape, not as a
service-level claim. Build time includes FTS construction and embedding computation for that
chunking group.

| Strategy | Chunks | Build ms | primary@1 | recall@3 | recall@5 | MRR | p95 ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| base · section · BM25 (runtime) | 203 | 25.7 | **77.5%** | **100.0%** | **100.0%** | **0.851** | 14.1 |
| expanded · section · BM25 | 2,603 | 2,868.2 | 52.5% | 80.0% | 82.5% | 0.626 | 9.2 |
| expanded · section · BM25 + rerank | 2,603 | 2,868.2 | 67.5% | 85.0% | 90.0% | 0.735 | 10.0 |
| expanded · section · dense only | 2,603 | 2,868.2 | 40.0% | 77.5% | 80.0% | 0.502 | 3.2 |
| expanded · section · hybrid (RRF) | 2,603 | 2,868.2 | 40.0% | 80.0% | 87.5% | 0.542 | 8.6 |
| expanded · section · hybrid + rerank | 2,603 | 2,868.2 | 65.0% | 87.5% | 92.5% | 0.728 | 8.8 |
| expanded · paragraph · BM25 | 717 | 2,145.1 | 70.0% | **97.5%** | **97.5%** | **0.789** | 5.5 |
| expanded · paragraph · BM25 + rerank | 717 | 2,145.1 | 62.5% | 95.0% | 95.0% | 0.723 | 9.0 |
| expanded · paragraph · hybrid + rerank | 717 | 2,145.1 | 65.0% | 92.5% | 92.5% | 0.742 | 8.8 |
| expanded · fixed · BM25 | 2,640 | 3,442.7 | 52.5% | 82.5% | 85.0% | 0.647 | 7.8 |
| expanded · fixed · BM25 + rerank | 2,640 | 3,442.7 | 65.0% | 87.5% | 90.0% | 0.723 | 9.0 |
| expanded · fixed · hybrid + rerank | 2,640 | 3,442.7 | 62.5% | 87.5% | 92.5% | 0.717 | 9.1 |

Full per-query rows are written to `data/evaluation_runs/rag_experiments.json` (ignored by Git).

## 5. What the numbers mean

1. **The curated corpus still wins on its own queries.** This is expected: the 40 golden queries
   were written against the 33-document corpus, and adding 480 plausible distractors can only make
   their job harder. The runtime corpus is therefore unchanged.
2. **Chunking is the largest effect on the larger corpus.** Paragraph-level chunks recover
   97.5% recall@3 against 80.0% for section-level BM25 with the same content. Coarser chunks reduce
   the number of near-duplicate sections competing on the same words.
3. **Dense-only retrieval is the weakest channel.** The hashing embedding captures lexical overlap
   and morphology, not meaning; it is not a substitute for a multilingual sentence model.
4. **Reranking helps when the first stage fragments the corpus.** Section BM25 improves from
   80.0% to 87.5% recall@3 and 52.5% to 65.0% primary@1. On paragraph chunks, where BM25 is already
   strong, reranking is slightly worse (97.5% to 95.0%), so it is not adopted blindly.
5. **Fusion does not automatically beat the better first stage.** RRF without reranking trails
   both BM25 variants; it adds dense-only candidates that are often wrong. The safe order is BM25
   candidates, then rerank, not dense union, then rerank.

The honest conclusion for the capstone: the measured upgrade path is useful when the corpus must
grow, and paragraph-level chunking is the first lever. The demo keeps the small curated corpus
because it is better on every metric and keeps citations easy for a reviewer to verify.

## 6. Runtime controls

The runtime defaults are unchanged:

- `BHARATBIZ_RAG_STRATEGY` unset or `bm25` → the original BM25 path.
- `BHARATBIZ_RAG_STRATEGY=dense|hybrid|hybrid_rerank|bm25_rerank` → the experimental chunk index.
- `BHARATBIZ_RAG_CHUNKS=section|paragraph|fixed` → chunking for the experimental path (default `section`).
- `BHARATBIZ_RAG_CORPUS=<path>` → optional additive corpus roots, separated by the OS path separator.

An unknown strategy value falls back to `bm25`. There is a test that the default `retrieve()` result
is identical to `RagIndex.search()` and that the default index does not contain Track B documents.

## 7. Reproduce

```bash
python scripts/build_track_b_corpus.py --check
python scripts/eval_rag_experiments.py --out data/evaluation_runs/rag_experiments.json
python scripts/eval_rag.py
python -m pytest tests/test_track_b_rag.py tests/test_rag.py -q
```

The canonical RAG evaluation still reports 33 documents, 203 sections, recall@3 100%, primary@1
77.5% and MRR 0.851, matching its existing test floors.

## 8. Limitations

- The golden set was authored for the curated corpus; it is a fair regression measure, not a
  benchmark for open-domain retrieval.
- The hashing embedding has no semantic or multilingual capability. Hinglish queries are not
  evaluated here.
- The additive corpus is generated by one script with one seed. It is diverse by document family,
  not independently authored, and should not be presented as real operational data.
- Latency was measured on one machine and is not a capacity claim.
- The reranker weights were fixed before the ablation and not tuned per strategy; a different
  corpus may need different weights.
