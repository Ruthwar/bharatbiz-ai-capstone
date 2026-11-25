# Track B evaluation report

Measured on 2026-11-24 against the frozen inputs below. No result in this report is estimated,
backfilled or carried over from an earlier run. Synthetic data is fictional; every outcome remains
advisory and requires a human reviewer.

## Frozen inputs

| Input | File | SHA-256 |
| --- | --- | --- |
| Track B gold set, 80 cases, version `track_b_gold_v1.1` | `data/eval/track_b/cases.jsonl` plus `manifest.json` | `59a127eb486a692f91cbb2be98f998cc116ce7ccadeed1f9327a82b8b7112aa7` |
| Held-out extraction set, 12 records | `data/eval/heldout_extraction.jsonl` | `2b1c2c45e8a258060fb86d818ec9b7a0082fe58534ece16d353c69acde270a19` |

The held-out labels were not used to choose prompts, few-shot examples or repair wording. The
few-shot examples come from scenario fixtures, not from the held-out records; a test enforces
that separation.

## Deterministic Track B gold run

Command:

```powershell
python scripts/eval_track_b.py --out data/evaluation_runs/track_b_after_validation_fix.json
```

| Group | Cases | Passed | Pass rate |
| --- | ---: | ---: | ---: |
| authority and security | 10 | 10 | 100.0% |
| canonical scenario | 15 | 15 | 100.0% |
| edge case | 5 | 5 | 100.0% |
| inbound persistence | 15 | 15 | 100.0% |
| intent variant | 10 | 10 | 100.0% |
| multi-turn | 10 | 10 | 100.0% |
| restatement | 15 | 15 | 100.0% |
| **Total** | **80** | **80** | **100.0%** |

Latency measured p50 184–399 ms and p95 283–625 ms across recorded runs on the same machine;
the pass result is stable, the timing depends on machine load. No exceptions and no failure labels.

This run includes two corrections made before the run: the credit flow now falls back to the
authenticated sender when the text has no retailer ID, and validation now rejects a well-formed but
unknown supplier or retailer ID instead of accepting it. The earlier recorded baseline of 79/80
belongs to the state before the credit fix; it is not restated as the current result.

## Held-out extraction and prompting comparison

Command:

```powershell
python scripts/eval_prompting.py --out data/evaluation_runs/prompting_strategies.json
```

Model: `Qwen/Qwen3-8B` through the college gateway. Token counts are the gateway's reported
`prompt_tokens` and `completion_tokens`. `record_exact` requires the primary intent and every
expected entity to match the label, including literal dates and quantities; it is intentionally
strict.

| Strategy | Intent accuracy | Stated-entity accuracy | Record exact | Validation pass | Fallbacks | Model calls | Total tokens | Tokens/example | p50 ms | p95 ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| rules | 41.7% | 30.4% | 8.3% | 58.3% | 0 | 0 | 0 | 0.0 | 0.5 | 2.8 |
| zero-shot | 58.3% | 34.8% | 0.0% | 83.3% | 2 | 12 | 10,095 | 841.2 | 2,067.8 | 4,292.8 |
| few-shot | 58.3% | 56.5% | 33.3% | 100.0% | 0 | 12 | 14,116 | 1,176.3 | 2,199.2 | 3,206.6 |
| zero-shot + repair | 58.3% | 34.8% | 0.0% | 83.3% | 2 | 14 | 11,801 | 983.4 | 2,045.4 | 6,774.2 |
| few-shot + repair | 58.3% | 56.5% | 33.3% | 100.0% | 0 | 12 | 14,119 | 1,176.6 | 2,268.5 | 3,227.8 |

Failure labels, counted per example and not mutually exclusive:

| Strategy | `reasoning_error` | `hallucination` | `tool_call_error` | `retrieval_miss` |
| --- | ---: | ---: | ---: | ---: |
| rules | 7 | 4 | 0 | 0 |
| zero-shot | 5 | 7 | 2 | 0 |
| few-shot | 5 | 3 | 0 | 0 |
| zero-shot + repair | 5 | 7 | 2 | 0 |
| few-shot + repair | 5 | 3 | 0 | 0 |

### What changed and what it cost

- Few-shot prompting improved stated-entity accuracy from 34.8% to 56.5%, strict record exact
  match from 0/12 to 4/12, and validation pass rate from 83.3% to 100%. It removed both zero-shot
  fallbacks. The cost was 14,116 tokens versus 10,095, a 40% increase, and about 6% higher p50
  latency.
- The few-shot examples were corrected before this run to follow the same contract as the system
  prompt: names in `supplier_name` / `retailer_name`, never invented catalogue IDs, and quantities
  as digits. The first run used IDs in the examples and scored 43.5% stated-entity accuracy; that
  run is not the reported result.
- Repair was triggered twice in zero-shot mode and succeeded zero times. The failures were
  messages with no classifiable intent; repeating the validation message did not make the model
  pick a category. Repair added 1,706 tokens in zero-shot mode with no accuracy change. Few-shot
  mode had no validation failure, so its repair variant never called the model twice.
- Rules extraction remains the cheapest path and the only one with no model dependency, but it
  classified 5 of the 12 held-out messages as unclassified and produced one exact match
  (HOLD-0005).
- Intent accuracy is identical at 58.3% for every LLM strategy: the remaining errors are label
  disagreements such as "two days late" being read as `supplier_delay` where the frozen label says
  `delivery_complaint`, not prompt-format effects.
- Strict entity matching is the main reason record-exact scores stay low. Labels keep literal
  phrases such as "Three", "4 bags", "today", "next visit" and "2026-10-29", while the extraction
  contract stores `quantity` as digits and does not infer dates. The comparison therefore reports
  both stated-entity accuracy and record exact match instead of hiding the difference.

## Cost policy

No cost is shown because no billing rate is configured. The college gateway does not return a
price. If an illustrative rate is supplied in `BHARATBIZ_TRACE_COST_PER_1K_TOKENS`, the harness
computes:

```text
estimated_cost = (prompt_tokens + completion_tokens) / 1000 * rate
```

Any such figure must be described as illustrative, not as the gateway's tariff.

## Agent and safety checks

Measured live on the same day:

- `python scripts/agent_review.py --intent supplier_delay --sku-id SKU-003 --supplier-id SUP-005 --delay-days 2`
  completed in 5 of 10 allowed tool calls, used 1,288 estimated tokens of 12,000, cited three
  in-force documents including `POL-DLY-001`, and recorded no failure label.
- `python scripts/eval_agent.py` ran 17 frozen agent tasks across every actionable intent:
  17/17 completed, 4.47 average tool calls, 1,060 estimated tokens per task, p50 156 ms and
  p95 219 ms with in-memory stores, zero exceptions and zero failure labels. The same evaluation
  through the API measured p50 250–422 ms and p95 297–500 ms across recorded runs because it
  uses durable stores.
- A follow-up question that repeats no identifiers resolved intent, SKU, supplier and delay from
  the persisted session, returned status `ok` and recorded `side_effects: false`.
- A supplied plan containing the unsupported tool `approve_order` was not executed. The runtime
  fell back to the deterministic plan, recorded `unknown_tool`, and still completed the five
  read-only steps.
- A request that omitted the intent ran as `baseline`; the critic rejected citations outside the
  baseline policy set with `retrieval_miss`. This is the taxonomy working, not a silent success.
  The demo command therefore passes `--intent supplier_delay`.
- Two successive `GET /api/v1/status` calls returned `X-Cache: miss` then `X-Cache: hit`;
  `GET /api/v1/safety/controls` reported the active cache, rate-limit, PII, injection and
  human-approval settings.
- `GET /api/v1/safety/corpus-audit` scanned all 33 documents and 203 sections; six sections
  matched injection heuristics (`autonomous_action` 5, `review_bypass` 1). The matches are policy
  and SOP phrasing such as "approve automatically", not injected attacks, and a flag changes no
  routing, approval or plan.

The failure taxonomy is therefore exercised at three levels: retrieval (`retrieval_miss`),
generation (`reasoning_error`, `hallucination`) and integration (`tool_call_error`,
`unknown_tool`). No failure silently approves or executes anything.

## Reproduce

```powershell
python -m pytest -q                         # 277 passed
python scripts/eval_track_b.py              # 80/80 deterministic gold cases
python scripts/eval_agent.py                # 17/17 agent tasks, completion and tool calls
python scripts/eval_prompting.py            # 12 held-out examples, five strategies
python scripts/eval_rag.py                  # frozen retrieval queries
python scripts/eval_rag_experiments.py      # corpus/chunking/hybrid/rerank comparison
```

The first run needs a configured model for the LLM strategies; without one, only the rules baseline
runs and the summary reports `llm_available: false`. Scripts default trace export to `none`; they do
not force the application's `LLM_PROVIDER` off.

## Limits

- The held-out extraction set has 12 records. It is enough for a directional comparison, not for a
  confidence interval or a claim of general model quality.
- Labels are literal and frozen. Improving the extractor to match them exactly, for example by
  accepting quantity words, would be a schema decision that must be agreed and re-frozen, not a
  silent grader change.
- The gold set measures deterministic decision behaviour on synthetic fixtures. It does not measure
  real-world accuracy, live retailer traffic or production latency.
- No live Langfuse export was exercised. Traces are local and Langfuse-shaped; see
  `docs/TRACK_B_SAFETY.md` and `README.md`.
- Docker images are defined but were not built in this environment; only static checks ran.

## Related documents

- `docs/TRACK_B_RAG_EXPERIMENTS.md` for retrieval experiments on the same gold set
- `docs/TRACK_B_AGENT_RUNTIME.md` for the planner/executor/critic budgets and failure taxonomy
- `docs/TRACK_B_SAFETY.md` for cache, rate limit, PII and prompt-injection controls
- `docs/PRESENTATION_RUNBOOK.md` for the timed walkthrough and `docs/PRESENTATION_SCRIPT_15MIN.md` for the spoken script
