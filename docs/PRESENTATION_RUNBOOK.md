# Presentation runbook — 15 minutes

BharatBiz Operations Console: channel intake → evidence extraction → candidate planning →
independent verification → human decision. Every number in this file was measured on this
machine on 2026-11-24 and is reproducible from the screen named beside it.

Companion script: `docs/PRESENTATION_SCRIPT_15MIN.md`.

## Preflight

```powershell
python scripts/check_llm.py
python -m uvicorn app.main:app --host 127.0.0.1 --port 8011
$env:BHARATBIZ_API_URL = "http://127.0.0.1:8011"
python -m streamlit run app/dashboard/chat.py --server.port 8511
```

The dashboard must point at **8011**, not the default 8000.

```powershell
curl.exe -s http://127.0.0.1:8011/api/v1/status
curl.exe -s http://127.0.0.1:8011/api/v1/safety/controls
```

Opening state on this machine: status and safety both HTTP 200; dashboard health `ok`; overview
shows 30 open order lines, 3 demand gaps, 5 pending reviews, ₹2,50,000 cash and ₹2,00,000
deployable cash. The five pending reviews are `credit_check`, `delivery_discrepancy`,
`short_dated_stock`, `demand_spike` and `batch_recall`.

Warm the evidence tabs before the session, in this order, so each tab opens on a completed run:

1. **Track B evidence → Gold set** (~30 s)
2. **Retrieval upgrades** (~60 s)
3. **Prompting strategies** (several minutes — start this early)
4. **Agent runtime** (seconds)

The job store lives in the API process. A restarted API returns no previous jobs, so rerun the
tabs or use the terminal commands in section 10.

Measurements to quote:

| Area | Measured result |
| --- | --- |
| Full test suite | 277 passed |
| Frozen gold set | 80/80, seven groups at 100%, zero failure labels |
| Gold-set latency | p50 184–399 ms, p95 283–625 ms across recorded runs |
| Retrieval | 513 documents, 2,603 sections, 3 chunkings, 12 strategies, 40 queries |
| Retrieval accuracy | base section BM25 recall@3 100%, precision@1 77.5%, MRR 0.851 |
| Rerank lift on the expanded corpus | precision@1 52.5% → 67.5%, recall@3 80% → 85% |
| Prompting | 12 held-out messages, 5 strategies, gateway-reported tokens |
| Few-shot effect | stated entities 34.8% → 56.5%, exact records 0/12 → 4/12 |
| Few-shot token cost | 10,095 → ~14,100 total tokens (+40%) |
| Agent evaluation | 17/17 tasks, 4.47 average tool calls, 1,060 estimated tokens per task |
| Agent latency | p50 250–422 ms, p95 297–500 ms across recorded runs |
| Agent review CLI | 5 of 10 tool calls, 1,288 estimated tokens, ~300 ms, 3 citations |
| Trace store | Live counters: several thousand spans, 400+ model generations, thousands of retrieval calls, hundreds of tool calls |
| Safety controls | 5 s read cache / 128 entries, 600 requests/min burst 200, 7 PII identifier types |
| Corpus audit | 203 sections audited, 6 flagged policy phrasings |

## Timed sequence

| Time | Segment | Screen | Evidence on screen |
| --- | --- | --- | --- |
| 0:00–1:00 | Opening and scope | Overview | 30 order lines, 3 gaps, 5 decisions, cash and deployable cash |
| 1:00–2:00 | Scope, control flow and safeguards | Overview + scenario coverage | Four scenario groups covering all 15; "Controlled decision flow"; validation and independent verification |
| 2:00–4:00 | SCN-003 Supplier delay, two decision policies | Scenario lab | Two plans, two suppliers, one-day and ₹533.60 trade-off, citations |
| 4:00–5:00 | SCN-010 Overdue retailer | Scenario lab | ₹57,448.23 overdue, ₹62,068.23 exposure against ₹50,000 limit |
| 5:00–5:40 | SCN-011 Scheme claim | Scenario lab | 10% claimed, 7.50% approved with a 40-unit minimum |
| 5:40–6:40 | SCN-013 Batch recall | Scenario lab | 300 pieces, 110 holdable, 4 open orders, quarantine |
| 6:40–7:20 | SCN-015 Dispatch capacity | Scenario lab | 40-unit van, 47 units of demand, 26 loaded, 1 order deferred |
| 7:20–8:20 | Intake, extraction and the review gate | Inbox | Verbatim spans, safety block, review queue |
| 8:20–9:50 | Agent runtime | Terminal + Agent runtime tab | 5 tool calls, 3 citations, rejected `approve_order`, follow-up turn |
| 9:50–12:20 | Evaluation evidence | Track B evidence | 80/80, 12 retrieval strategies, 5 prompting strategies, 17/17 tasks |
| 12:20–13:30 | Observability and safety controls | LLM observability, Safety controls | Traces, cache miss→hit, PII mask, injection preview |
| 13:30–14:20 | Architecture and responsible AI | Track B evidence header | Containers, rate limit, advisory-only actions, human approval |
| 14:20–15:00 | Close | Overview / Decision desk | Every case `pending_review`; no business action taken |

## 1. Opening (0:00–1:00)

Open **Overview**. Point at the five metric cards in one sweep, left to right.

Say: demand, stock exposure, cash protection and open decisions in one view; 30 open order
lines across four retailers, 3 demand gaps, 5 decisions waiting for a person, ₹2,50,000 cash of
which ₹2,00,000 is deployable above the ₹50,000 buffer.

Do not explain the architecture yet. Let the numbers establish that this is an operating
console, not a prototype screen.

## 2. Scope, control flow and safeguards (1:00–2:00)

Stay on **Overview**. Name the four scenario groups and the fifteen cases inside them: core
operations (SCN-001, 002, 003, 015), constraints and disruption (SCN-004, 005, 008, 014), retail
case review (SCN-006, 010, 011, 012) and market and quality signals (SCN-007, 009, 013). Note that
five are opened live in this session and the deck's coverage slide maps all fifteen.

Then scroll to **Controlled decision flow**.

Read the five stages aloud: `channel intake → evidence extraction → candidate planning →
independent verification → human decision`.

Then the two safeguards:

- Extraction output must pass deterministic checks: verbatim evidence spans, catalogue
  authority, known supplier and retailer IDs, valid day counts.
- Verification reconstructs the plan independently; it does not trust the model.

Say: the model can propose, but deterministic code decides whether the proposal is usable.

## 3. SCN-003, same evidence, two decision policies (2:00–4:00)

**Scenario lab** → Scenario **SCN-003 · Supplier delay** → Recommendation mode **Deterministic**
(in the sidebar) → **Run selected scenario**.

Measured deterministic outcome:

- Buy 46 litres from **Balaji Wholesale Distributors (SUP-002)** at **₹4,876.46**, arrival
  2026-11-25.
- 102/102 units fulfilled, 0 unfilled, 28 late.
- Fixed ranking: fewest unfilled, then fewest late, then earliest arrival, then lowest cost.
- No citations; policy passages are context only.

Then switch the sidebar mode to **Policy-grounded LLM** and press **Run selected scenario**
again.

Measured policy-grounded outcome:

- Buy 46 litres from **Sri Venkateswara FMCG Supply (SUP-005)** at **₹4,342.86**, arrival
  2026-11-26.
- 102/102 units fulfilled, 0 unfilled, 28 late.
- Explicit priority: cost; projected headroom **₹1,95,657.14**.
- Stated trade-off: SUP-002 costs **₹533.60** more but arrives one day earlier.
- Cites `POL-CST-010`, `POL-DLY-001` and `POL-CSH-002`.
- Still `pending_review`.

Say: deterministic is a fixed policy, not the absence of policy. The grounded mode can trade a
day of arrival against ₹533.60 using cited rules, and it shows the trade-off instead of hiding
it.

## 4. SCN-010 Overdue retailer (4:00–5:00)

Scenario **SCN-010 · Overdue retailer with new order**, mode **Policy-grounded LLM**, run.

Measured:

- RET-016 already owes **₹57,448.23** past due.
- The new 30 kg order is worth **₹4,620.00** and would raise exposure to **₹62,068.23**.
- The credit limit is **₹50,000.00**.
- Recommendation: hold the new order for a human credit decision.
- Cites `POL-LIQ-007` and `POL-SVC-009`.

Say: no order is accepted, no credit decision is executed and nothing is sent to RET-016.

## 5. SCN-011 Scheme claim (5:00–5:40)

Scenario **SCN-011 · Scheme claim mismatch**, mode **Deterministic**, run.

Measured:

- Claim on `SCM-002`: 10% off 30 units.
- Approved scheme: **7.50%** with a **40-unit minimum**.
- Routed to `scheme_claim_review`; the decision-mode selector does not apply because this case
  produces no operational plan.

Say: the console does not stretch a scheme to fit a claim. It shows the gap and routes it to a
person.

## 6. SCN-013 Batch recall (5:40–6:40)

Scenario **SCN-013 · Batch recall and quality hold**, mode **Policy-grounded LLM**, run.

Measured:

- Recall `RCL-001` covers batch **BATCH-004**, 300 pieces of SKU-005.
- **110 unreserved pieces** can be held; **4 open orders** use the SKU.
- Recommendation: quarantine the batch. Release is infeasible while the recall requires the
  batch held.
- Cites `POL-STK-007`.

Say: the recall path protects stock first and never re-allocates a recalled batch.

## 7. SCN-015 Dispatch capacity (6:40–7:20)

Scenario **SCN-015 · Dispatch under vehicle capacity**, mode **Deterministic**, run.

Measured:

- Route `RTE-001`, van `AP-09`: **40 units** capacity, **47 units** of demand across 3 orders.
- 7 feasible load plans; none ships all 47 units.
- Selected **ORD-0001 + ORD-0018**: 26 units loaded, 1 order deferred, 0 promise risk.
- The grounded mode cites `POL-SVC-009`; deterministic uses the fixed service ranking.

Say: the console does not promise what the van cannot carry.

## 8. Intake and the review gate (7:20–8:20)

Open **Inbox**. Expand **Example messages**, press **Load editable example** for the supplier
delay message. Keep the sender visible and submit.

Show, in order:

- The extracted facts with exact evidence spans from the message.
- A clarification question when a required slot is missing (choose a message without a SKU).
- The advisory **safety** block: prompt-injection and PII signals are counts, not routing
  changes.
- The review queue entry. Approval or rejection is a person's action and changes only review
  state.

Say: the message body is not stored in traces, and PII is masked before any external model call.

## 9. Agent runtime (8:20–9:50)

Terminal:

```powershell
python scripts/agent_review.py --intent supplier_delay --sku-id SKU-003 --supplier-id SUP-005 --delay-days 2
```

Measured: status `ok`, 5 of 10 tool calls, 1,288 estimated tokens, ~300 ms, three in-force
citations including `POL-DLY-001`, no failure labels. Budgets are 10 calls, 12,000 estimated
tokens and 5 seconds; the token figure is a characters/4 estimate, not provider billing.

Failure path:

```powershell
python scripts/agent_review.py --intent supplier_delay --sku-id SKU-003 --supplier-id SUP-005 --delay-days 2 --plan docs/fixtures/malformed_agent_plan.json
```

Measured: plan source `deterministic_fallback`, label `unknown_tool`, all five safe steps still
execute. The unsupported `approve_order` tool never runs.

Then **Track B evidence → Agent runtime** and press **Ask a follow-up without repeating the
identifiers**. The next turn resolves intent, SKU, supplier and delay from the session store;
the request repeats none of them; status `ok` and `side effects: False`.

Say: seven read-only tools, planner → executor → critic, one retry round, persistent state, and
a hard stop at ten steps.

## 10. Evaluation evidence (9:50–12:20)

**Track B evidence**.

| Tab | Show | Measured result |
| --- | --- | --- |
| Gold set | Press **Run gold set** if no completed run is shown | 80/80; groups 10/15/5/15/10/10/15 all at 100%; dev 60/60, confirm 20/20; zero failure labels; p50 184–399 ms, p95 283–625 ms across recorded runs |
| Retrieval upgrades | Strategy table | 513 documents, 2,603 sections, 12 strategies, 40 queries; base section BM25 recall@3 100%; rerank lifts expanded-corpus precision@1 52.5% → 67.5% and recall@3 80% → 85%; paragraph chunking reaches 97.5% recall@3 |
| Prompting strategies | Strategy comparison | 12 held-out messages, 5 strategies; few-shot stated entities 34.8% → 56.5%, exact records 0/12 → 4/12, tokens 10,095 → ~14,100 (+40%); validation passes on all 12 |
| Agent runtime | 17-task table | 17/17 completed, 4.47 average tool calls, 1,060 estimated tokens per task, p50 250–422 ms, p95 297–500 ms across recorded runs, zero exceptions |
| Safety controls | Cache probe, audit, PII mask | `X-Cache: miss → hit`; 203 sections audited, 6 flagged; 7 identifier types masked; injection detection advisory |

Terminal equivalents:

```powershell
python scripts/eval_track_b.py --out data/evaluation_runs/track_b_after_validation_fix.json
python scripts/eval_prompting.py --out data/evaluation_runs/prompting_strategies.json
python scripts/eval_agent.py --out data/evaluation_runs/agent_evaluation.json
```

The gold set is frozen: dataset
`59a127eb486a692f91cbb2be98f998cc116ce7ccadeed1f9327a82b8b7112aa7`, 80 cases, rules-only,
environment-independent. Reruns reproduce the pass rate; latency varies with machine load, so
quote the range.

## 11. Observability and safety controls (12:20–13:30)

Open **LLM observability**. The counters are live: several thousand spans, 400+ model generations,
thousands of retrieval calls and hundreds of tool calls. Span latency sits around p50 2.3 s and
p95 5.1 s. Read the current figures from the page rather than a fixed total.
Open one trace to show the span sequence.

Then **Track B evidence → Safety controls**:

- Cache probe: first `GET /api/v1/status` returns `X-Cache: miss`, second `hit`.
- Corpus audit: 203 sections, 6 flagged policy phrasings (`autonomous_action` 5,
  `review_bypass` 1). These are policy and SOP sentences such as "approve automatically" that
  the detector matches. A flag never changes routing, approval or a plan; retrieved passages
  are treated as data.
- PII mask preview: 7 identifier types.
- Injection preview: advisory only; counts, not routing changes.

```powershell
curl.exe -s http://127.0.0.1:8011/api/v1/safety/controls
curl.exe -s http://127.0.0.1:8011/api/v1/safety/corpus-audit
```

## 12. Architecture and responsible AI (13:30–14:20)

Say:

- Streamlit console over a FastAPI service; SQLite stores for state, reviews, sessions and
  traces.
- Container definitions pin `python:3.12.10-slim`, run as a non-root user, copy only required
  paths, and contain no credentials.
- Read cache 5 s / 128 entries; 600 requests per minute with burst 200; seven PII identifier
  types masked before external calls.
- Every recommendation is advisory. Approval changes review state only. No purchase, payment,
  price change, stock mutation or outbound message is executed by the system.

The header on every Track B tab states the same boundary: read-only, no business actions,
human approval required.

## 13. Close (14:20–15:00)

Return to **Overview** or **Decision desk**. Point at a review card and read the footer:
"No purchases · payments · stock mutations · outbound messages".

Say: intake is automated, evidence is verified, planning is compared, and the final decision
stays with a person. Every scenario in this session ended `pending_review` — the review gate is
the product, not a checkpoint bolted on at the end.

## Contingencies

| Situation | Action |
| --- | --- |
| Gateway slow or unavailable | Switch Recommendation mode to **Deterministic**; extraction falls back to rules and labels the uncertainty. The workflow still completes. |
| Agent reports `retrieval_miss` | Pass an explicit `--intent`; without it the agent defaults to `baseline`, which is not the supplier-delay policy set. |
| HTTP 429 | Wait for `Retry-After`; do not fire parallel curls. |
| UI looks stale for a few seconds | The read cache is 5 s and is cleared by any write. |
| API returns 404 or a stale route | Restart `uvicorn` on 8011; confirm the dashboard still points at 8011. |
| Evaluation tab shows no run | Press the run button, or use the terminal commands in section 10. |

## Coverage map

| Instruction area | Where it is shown | Evidence |
| --- | --- | --- |
| I. Problem framing, scope and data | Overview + Scenario lab + Gold set | 15 scenarios, 80 frozen cases, 7 groups at 100% |
| II. Prompting strategies | Prompting strategies tab | Rules, zero-shot, few-shot, and both model prompts with one repair round; per-strategy accuracy, tokens and labels |
| III. Retrieval-augmented generation | Retrieval upgrades tab | 513 documents, 2,603 sections, 3 chunkings, BM25 + dense + RRF + rerank, 40 frozen queries |
| IV. Agentic layer | Agent runtime tab + CLI | 7 read-only tools, planner → executor → critic, persistent state, labelled failures, 10-step cap |
| V. Evaluation and observability | Gold set, Prompting, Agent runtime, LLM observability | Accuracy, task completion, tool calls per task, tokens and latency, four-category taxonomy, traces |
| VI. Shipping and responsible AI | Safety controls + review gate | Cache and rate limit, injection audit, PII masking, no-action checks, human approval |

## End state

Every scenario ends `pending_review`. The console footer reads "No purchases · payments · stock
mutations · outbound messages". Approval changes review state only.
