# Track B agent runtime: tools, planner, executor, critic

The agentic layer is a bounded, read-only review loop. It exists so the reasoning behind a
review can be inspected step by step, not so the system can act. No tool places an order,
pays a supplier, changes stock, sets a price, decides credit or messages a party. Approval
remains a human action in the review ledger, and the runtime never calls it.

Code: `app/agent_runtime/` (registry, planner, executor, critic, runtime, session store).
HTTP surface: `app/agent_api.py`. CLI: `scripts/agent_review.py`. Tests:
`tests/test_agent_runtime.py`.

## 1. Tool catalogue

Seven tools, all read-only. Each is a thin adapter over an existing deterministic function;
the tool adds validation and a trace span, not arithmetic.

| Tool | Returns | Underlying function |
| --- | --- | --- |
| `policy_search` | Verbatim policy/SOP citations in force on the decision date | `app.rag.retrieval.retrieve` |
| `policy_metadata` | Applicable, not-yet-effective and out-of-scope documents for the event | `app.decision.selector.policy_inventory` |
| `inventory_position` | On-hand, reserved, incoming, ATP, immediately available units | `app.agents.inventory.analyze_inventory` |
| `open_orders` | Open orders, quantities, dates and priority for one SKU | `app.agents.orders.analyze_orders` |
| `supplier_options` | Read-only supplier offers with lead time, arrival and cost | `app.agents.supplier.build_supplier_options` |
| `cash_position` | Ending cash and headroom above the minimum buffer | `app.agents.cashflow.project_cash` |
| `retailer_profile` | Retailer record, open allocations and order history | `app.agents.retailer` helpers |

`policy_search` defaults to `policy` and `sop` documents. Case notes, term sheets and
training notes stay available when a caller asks for them, but a rule citation is not taken
from a case note. Every citation carries a document id, heading, verbatim quote, effective
date and licence.

Arguments are validated against each tool's declared parameters before the handler runs:
unknown tools, unknown arguments, missing required arguments and wrong types produce a
labelled failure rather than a stack trace.

## 2. The loop

```
request ──▶ plan ──▶ execute ──▶ critique ──▶ (one retry of retryable steps) ──▶ critique ──▶ report
              │                      │
      deterministic rules     deterministic checks
      or supplied JSON        (coverage, citations, figures)
```

- **Planner.** Rules, not a model. The same request yields the same ordered steps. A SKU
  adds inventory and open orders; a supplier with a delay adds supplier options; a retailer
  adds the retailer profile; a cash outflow adds the cash projection. Missing identifiers
  become clarification requests, not invented values.
- **Executor.** The only place tools run. It resolves two derived arguments from prior
  observations (`required_units = open demand - immediately available`, and the planning
  horizon from the latest requested delivery date), enforces the caps, and records every
  attempt as an observation.
- **Critic.** Checks that every planned step ran, no tool failed, the run cites at least one
  document from the applicable policy set, every citation has a quote/licence/effective date
  and is in force, and the returned figures are internally consistent (order totals,
  inventory demand baseline, cash headroom, supplier cost arithmetic).
- **Retry.** At most one round, and only for findings that a retry can fix: a retrieval miss
  or a transient tool failure. The policy query is widened with the intent phrase and the
  top-k is raised. Structural findings (inconsistent figures, unsupported citation) are not
  retried because rerunning cannot change them.

Supplied plans are accepted for experimentation (for example a small model's JSON) but are
validated first. Malformed JSON, an unknown tool, bad arguments or more than ten steps fall
back to the deterministic plan and are recorded as labels. They do not crash the request.

## 3. Budgets

| Cap | Value | Enforcement |
| --- | --- | --- |
| Steps per query | 10 | Checked before every tool call; remaining steps are `skipped` |
| Estimated tokens | 12,000 | Characters / 4, charged for arguments and output |
| Wall clock | 5 s | Checked before every tool call |
| Identical calls | 2 | A third identical call is refused with `loop_guard` |

Token use is an estimate, not provider billing. It is labelled `characters/4 (deterministic
estimate, not provider-billed)` in every report. Skipped steps are visible in `steps` and
produce a `step_cap`, `token_cap` or `time_cap` label.

## 4. Persistent state across turns

`app/agent_runtime/store.py` keeps one SQLite row per turn in
`data/runtime/agent_sessions.sqlite3` (override with `BHARATBIZ_AGENT_DB`). A row stores the
question, intent, status, resolved context (intent, SKU, supplier, retailer, delay, required
units, outflow) and a compact run summary. The next turn on the same `conversation_id`
reuses those identifiers, so a follow-up such as "what if the delay becomes four days?" does
not need the SKU repeated. The store holds no approval and no business action. `POST
/api/v1/demo/reset` clears it.

## 5. Failure taxonomy

`failure_labels` names the concrete defect; `failure_taxonomy` maps each label to the Track B
taxonomy used in the evaluation report.

| Label | Taxonomy | Meaning |
| --- | --- | --- |
| `retrieval_miss` | retrieval miss | No passage, or no applicable passage, was retrieved |
| `citation_out_of_force` | retrieval miss | A cited document is not effective on the decision date |
| `unsupported_citation` | hallucination | A citation lacks a quote, licence or effective date |
| `inconsistent_figures` | reasoning error | Returned figures disagree with each other |
| `missing_identifier` | reasoning error | The review needs a SKU, supplier, retailer or delay |
| `plan_coverage` | reasoning error | A planned step did not run, or the plan omitted policy search |
| `tool_error`, `not_found`, `invalid_argument`, `malformed_arguments`, `unknown_tool`, `internal_error`, `policy_unavailable` | tool-call error | Tool execution or argument failure |
| `loop_guard`, `step_cap`, `token_cap`, `time_cap`, `budget_exhausted` | tool-call error | Budget or loop protection stopped the run |
| `malformed_json`, `invalid_plan` | tool-call error | A supplied plan could not be parsed or validated |

## 6. Measured example

Run on 2026-11-24 against the synthetic state `synthetic-v3-live-20261123`, saved in
`data/evaluation_runs/agent_runtime_example.json`:

```
question: The supplier says the cooking oil delivery is delayed by two days; what can we commit?
intent:   supplier_delay   SKU-003   supplier SUP-005   delay 2 days
```

| Observation | Value |
| --- | --- |
| Status | `ok`; no failure labels; one critic pass, no retry |
| Steps | 5 tool calls: metadata, policy search, inventory, orders, supplier options |
| Stock | 62 on hand, 6 reserved, 12 incoming delayed, 56 immediately available, 68 ATP |
| Demand | 102 units across 6 open orders |
| Uncovered | 46 units |
| Supplier options | SUP-002 ₹4,876.46; SUP-003 ₹4,708.10; SUP-005 ₹4,342.86, all 46 units and feasible |
| Citations | POL-DLY-001, POL-DEC-008 and POL-SVC-009, all effective 2026-10-15 and licensed |
| Estimated tokens | 1,360 of 12,000 |
| Elapsed | 453 ms in-process |

The numbers match the SCN-003 planning story (102 requested, 56 usable, 46 bought). The
elapsed time is local and will vary by machine; the token count is an estimate. The runtime
reports the evidence, not a selected plan: selection and verification remain in the decision
module.

## 7. Using it

API:

```bash
curl -s http://127.0.0.1:8011/api/v1/agent/tools
curl -s -X POST http://127.0.0.1:8011/api/v1/agent/review \
  -H "Content-Type: application/json" \
  -d '{"question":"The cooking oil supplier is two days late; what can we commit?","sku_id":"SKU-003","supplier_id":"SUP-005","delay_days":2,"conversation_id":"demo-1"}'
curl -s http://127.0.0.1:8011/api/v1/agent/sessions/demo-1
curl -s -X POST http://127.0.0.1:8011/api/v1/agent/plan/validate \
  -H "Content-Type: application/json" -d '{"plan":"{bad json"}'
```

CLI:

```bash
python scripts/agent_review.py --sku-id SKU-003 --supplier-id SUP-005 --delay-days 2 \
  --intent supplier_delay --question "The supplier reports a two-day delay; what can we commit?"
```

Every run also writes local spans (`agent` and `tool` kinds) through the existing trace
store, so the observability tab and `GET /api/v1/observability` include the loop without a
second tracing system.

## 8. What the tests prove

`tests/test_agent_runtime.py` covers 19 cases: the registry allow-list and argument
rejection, deterministic tool output and no review-queue writes, fixed plan order,
clarification for missing identifiers, malformed-JSON fallback, strict supplied-plan
validation, step and token caps, the loop guard, a critic retry that recovers, a tool failure
recorded without raising, two-turn context reuse, the API surface, agent/tool spans, and
demo reset. The full repository suite passes (236 tests).

## 9. Limits

- The planner is deterministic. Comparing prompting strategies for a model-proposed plan is
  the next evaluation; the supplied-plan path and `/api/v1/agent/plan/validate` exist for it.
- The critic checks structure and citations, not whether a recommendation is commercially
  wise. Plan selection and independent verification remain in `app/decision/` and
  `app/verification/`.
- The top retrieved section can be a worked example rather than the rules section; the quote
  is still verbatim and in force, and the ranking limitation is recorded in
  `docs/RAG_EVALUATION.md`.
- Token counts are estimates. Latency is local wall clock, not an endpoint SLA.
- No tool is stateful, so re-running a review cannot change the business state. The one
  durable write is the session turn itself.
