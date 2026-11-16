# RAG evaluation: proving the citations earn their place

The corpus is not there to make answers sound authoritative. It is there so a reviewer can check the rule behind a recommendation without leaving the card. This note records what was measured, on what, and what would count as failure.

## 1. What "worth it" means here

Three separate claims, each measured differently:

1. **Retrievable** — for a question a reviewer would actually ask, the right document is near the top.
2. **Citable** — every reference shown carries a document id, an effective date, a quote and a licence; the quote is verbatim, not paraphrased.
3. **Load-bearing** — the cited sections correspond to the rules the planner actually applied, so a reviewer can audit the decision rather than admire the prose.

A high retrieval score with a citation that does not justify the card would fail claim 3. A perfect citation on a document the reviewer never needed would fail claim 2's purpose.

## 2. Setup

| Item | Value |
| --- | --- |
| Corpus | 30 documents, 186 sections, 88.6 KiB |
| Index | SQLite FTS5, BM25, porter + unicode61 |
| Ranking | best section per document; sections must cover at least 35% of query content words |
| Query construction | per-intent template plus extracted fact values; top 3 documents shown on the card |
| Golden set | 40 queries, `data/eval/golden_queries.json`, written before measurement |
| Labels | each query names a primary document and a list of other documents that also answer it |
| Command | `python scripts/eval_rag.py` |

Labels were not tuned to the ranking. Where a question is genuinely answered by more than one document — the delay notice requirement appears in both POL-DLY-001 and the supplier terms — the duplicates are recorded as `acceptable` and counted for recall, but not for primary@1.

## 3. Results

Measured 2026-11-15 on the expanded corpus:

| Metric | BM25 (shipped) | Term-frequency baseline |
| --- | --- | --- |
| primary@1 | **77.5%** | 62.5% |
| recall@3 | **100.0%** | 90.0% |
| recall@5 | **100.0%** | — |
| MRR | **0.855** | 0.768 |
| latency p50 | **1.1 ms** warm, 3.4 ms cold | — |
| latency p95 | **2.0 ms** warm, 5.4 ms cold | — |

The baseline is the obvious alternative: count query words in the whole document and sort. BM25 remains stronger on the expanded corpus. The original 30-query slice retains 100% recall@3 and remains above the repository's primary@1 and MRR test floors; the absolute primary@1 change reflects the additional, intentionally overlapping policy/SOP documents.

### Ablation: the coverage filter

Before adding the 35% coverage requirement, a short case-note section could outrank a policy on one incidental word. GQ-12 ("maximum number of follow-up questions before human triage") ranked the SOP second behind a case note that happened to contain "following week".

| | primary@1 | MRR | GQ-12 rank |
| --- | --- | --- | --- |
| Without coverage filter | 76.7% | 0.840 | 2 |
| With coverage filter | 80.0% | 0.858 | 1 |

### Citation compliance on a real card

Running SCN-003 through the workflow and building the review context:

| Check | Result |
| --- | --- |
| References shown | 3 |
| With document id, effective date and licence | 3 / 3 |
| With a non-empty verbatim quote | 3 / 3 |
| In force on the scenario date (2026-11-01) | 3 / 3 |
| Documents | POL-DLY-001, POL-CSH-002, CASE-2026-014 |

### Citation-to-decision mapping

This is the load-bearing test, done by inspection against the card's own fields:

| Card element | Rule it must match | Cited section |
| --- | --- | --- |
| 102 requested, 56 usable, 46 bought | verify against state, not the message | POL-DLY-001 §3 R2 |
| 28 late units, all plans tied | fixed lexicographic ranking | POL-DLY-001 §3 R4 |
| Selected plan costs more than an alternative | show what the extra rupees buy | POL-DLY-001 §3 R6 |
| Headroom above ₹50,000 | exclude unaffordable plans before ranking | POL-CSH-002 §3 R1 |
| Revised date shown as unknown | never promise an unconfirmed date | POL-DLY-001 §3 R1 |
| Why 28 late units were accepted | the trade-off was time, not price | CASE-2026-014 §3 |

All six map to one of the three cited documents, so a reviewer can verify each line without opening a PDF.

### Coverage for the added scenario controls

The new golden queries and policy/SOP pairs extend the same citation-to-decision contract:

| Decision area | Decision field or claim | Primary citation | Procedure citation |
| --- | --- | --- | --- |
| Demand simulation | Baseline, assumption, state version and scenario outputs remain separate | POL-DEM-007 §3 R1-R6 | SOP-DEM-007 §2 |
| Physical stock | Counted, reserved and approved usable stock | POL-STK-007 §3 R2-R6 | SOP-STK-007 §2 |
| Liquidity | Opening cash, immediate outflow, ending cash and headroom | POL-LIQ-007 §3 R1-R5 | SOP-LIQ-007 §2 |
| Retailer complaints | Evidence, case ownership and human-approved remedy | POL-RCM-007 §2 R1-R7 | SOP-RCM-007 §2 |
| Market signals | Independent corroboration, duplicate handling and uncertainty | POL-MSC-007 §2 R1-R7 | SOP-MSC-007 §2 |

These mappings are labelled before measurement in `data/eval/golden_queries.json`; they are not generated from the observed ranking.

## 4. Where it fails

| Query | Observed | Cause | Consequence |
| --- | --- | --- | --- |
| GQ-01 promise a date | POL-DLY-001 outside top 5; SOP-SHT-003 first | the same rule is restated in the SOP and all three term sheets | acceptable answer first, canonical policy not shown |
| GQ-02 how an unconfirmed date is recorded | terms sheet first | short sections beat the long policy under BM25 length normalisation | acceptable, but the policy is the better citation |
| GQ-10 acknowledgement contents | CASE-2026-009 first | a short case section shares "delivery date" vocabulary | first citation is noise; POL-COM-006 is second |

The pattern is consistent: BM25 prefers short sections that repeat the query's words, and the synthetic term sheets repeat policy language on purpose. Two fixes are available and deliberately not taken yet:

- aggregate document score across sections instead of taking the best section, which rewards a rule that appears in several places;
- a reranker or multilingual embeddings, which would also help Hinglish queries that share no tokens with an English policy.

Neither is needed for the demo. Both are recorded here so the limitation is a known cost, not a surprise.

## 5. What would falsify the claim

- `tests/test_rag.py` fails if recall@3 drops below 93%, primary@1 below 70%, or MRR below 0.78. Current values are well above those floors.
- A review card that cites a document not in force on the decision date is a defect; the `as_of` filter exists for that and is tested.
- A card that shows a quote not present verbatim in the cited section is a defect. Quotes are extracted from the indexed text, not generated.
- A golden query that is edited after seeing the ranking would invalidate the measurement. The file is dated and versioned; changes require re-running the evaluation and noting it.

## 6. Cost

88.6 KiB, 30 files, one SQLite table, no embedding model, no network call, sub-2 ms warm-query latency in this run, same answer every time. The corpus remains small enough for a deterministic lexical index and checkable citations.

## 7. Next, if the corpus grows

1. Add a document-level score so a rule spread across sections outranks a one-line mention.
2. Add embeddings for Hinglish and Hindi message text (`bge-m3` or `multilingual-e5`), keeping BM25 as the exact-term channel.
3. Add a retrieval-quality gate per intent: if the top score is below a calibrated floor, show "no policy matched" rather than a weak citation. The current card already distinguishes the two, but the floor is not calibrated.
4. Have a domain reviewer label 50 real questions. Thirty self-written queries prove the pipeline works; they do not prove it covers what a distributor's staff actually asks.
