# SCN-003 Supplier Delay: Design Document

Status: implemented vertical slice, rules-only mock mode, no model key required.

This document explains how the first demo works end to end and which parts of the implementation carry forward when the project moves to real messages, an LLM, and retrieval-augmented generation (RAG).

## 1. Purpose

SCN-003 answers one operational question:

> A supplier reports a two-day delay on one product. Given current stock, open retailer orders, listed supplier alternatives, and the cash buffer, what should the distributor consider, and is that proposal defensible?

The demo is designed to show four things:

1. The original message is preserved exactly; extracted facts point to exact character spans.
2. Missing information stays missing. The system does not invent a revised date, quantity, SKU, or purchase order.
3. Every number in the recommendation is recomputed from the synthetic business state.
4. A human approves or rejects; the system never purchases, pays, updates stock, prices, extends credit, or messages a supplier or retailer.

## 2. Scope and non-goals

In scope:

- One message type: supplier delay.
- One catalogue resolution: product label to SKU.
- One product family affected per message.
- Deterministic inventory, order, supplier, cost, and cash analysis.
- Deterministic candidate generation and ranking.
- Independent verification of the selected plan.
- CLI, HTTP API, and Streamlit entry points.
- Synthetic data only.

Out of scope for this slice:

- Live ERP, WhatsApp, email, or supplier portal integration.
- Automatic purchase orders, payments, price changes, credit decisions, or stock mutations.
- Outbound messages of any kind.
- LLM extraction, embeddings, or vector search.
- Multi-product or multi-shipment optimization.
- Persistence of approvals.
- Real personal or commercial data.

## 3. Inputs

### 3.1 Message contract

`MessageSubmission` in `app/schemas/contracts.py` requires:

| Field | Meaning |
|---|---|
| `message_id` | Stable source identifier |
| `source_type` | One of `retailer_message`, `sales_visit`, `supplier_update`, `synthetic` |
| `text` | Verbatim source text |
| `observed_at` | Timezone-aware timestamp |
| `language` | Source language |
| `consent_status` | `synthetic`, `authorized`, or `not_applicable` |
| `state_version` | Version of the operational state the request is evaluated against |

Money never appears in the message contract. It comes from the versioned state.

### 3.2 Canonical fixture

`data/synthetic/scenario_fixtures/SCN-003.json` holds the demo message and the explicit simulation assumptions:

```json
{
  "scenario_id": "SCN-003",
  "message": {
    "message_id": "DEMO-SCN-003-001",
    "source_type": "supplier_update",
    "text": "Sri Venkateswara FMCG Supply reports a two-day delay for Cooking oil 1 L pouch; revised date is not confirmed.",
    "observed_at": "2026-11-01T09:00:00+05:30",
    "language": "English",
    "consent_status": "synthetic",
    "state_version": "synthetic-v2-seed-20261105"
  },
  "assumptions": {
    "sku_id": "SKU-003",
    "original_supplier_id": "SUP-005",
    "delayed_incoming_units": 12,
    "planning_horizon": "2026-11-04",
    "procurement_costs": "immediate_outflow"
  },
  "unknowns": [
    "supplier_confirmed_revised_delivery_date",
    "source_stated_delayed_quantity",
    "purchase_order_reference"
  ]
}
```

The CLI and dashboard read the message from this fixture. The current workflow does not read the `assumptions` block at runtime; it derives the same values from state as described in section 6.3. The fixture is therefore the documented contract for the simulation, not a configuration input yet. Section 13.3 explains the change needed to make it authoritative.

### 3.3 Operational state

`load_business_state()` in `app/state.py` loads a versioned synthetic snapshot:

- `business_state.json`: state version, as-of date, opening cash, minimum cash buffer.
- `products.csv`: catalogue, pack descriptions, base units, unit costs.
- `inventory.csv`: on hand, reserved, incoming, reorder point.
- `open_orders.csv`: open retailer orders.
- `suppliers.csv`: supplier master data.
- `supplier_products.csv`: listed offers with MOQ, capacity, lead time, unit cost.

Relevant values for this scenario:

| Item | Value |
|---|---|
| State version | `synthetic-v2-seed-20261105` |
| As-of date | 2026-11-01 |
| Opening cash | ₹250,000.00 |
| Minimum cash buffer | ₹50,000.00 |
| SKU-003 on hand | 62 litres |
| SKU-003 reserved | 6 litres |
| SKU-003 incoming | 12 litres |
| Open SKU-003 orders | 6 orders, 102 litres |

Monetary values are parsed as `Decimal` rupees. Integers are parsed as integers. Duplicate primary keys fail the load. A version mismatch fails the request.

## 4. Design principles

1. **Evidence before inference.** Facts are exact substrings of the source with offsets. Anything else is an inference, an assumption, or an unknown.
2. **Deterministic core.** Same message plus same state produces the same IDs, options, ranking, and totals.
3. **Separate thinking from arithmetic.** Specialist agents compute; they do not decide. The optimizer decides among explicit candidates.
4. **Independent verification.** The verifier recomputes from original state and orders; it does not trust the plan it is given.
5. **Human authority.** The output is a recommendation, never an action.
6. **Exact money.** `Decimal` rupees with two decimal places, no floats.
7. **No invented facts.** Null stays null. Unknown stays unknown.

## 5. End-to-end flow

```text
MessageSubmission
  -> event typing (rules)
  -> evidence extraction (regex, exact spans)
  -> catalogue resolution (label -> SKU)
  -> clarification gate (missing or ambiguous)
  -> state load with version check
  -> inventory analysis
  -> open-order analysis
  -> supplier option construction
  -> candidate plan construction (stock-only + feasible supplier plans)
  -> deterministic ranking
  -> independent verification
  -> recommendation (pending human review)
  -> API / CLI / dashboard
```

The returned trace is fixed for the happy path:

```text
received
state_loaded
event_extracted
specialists_completed
candidates_optimized
independently_verified
pending_human_review
```

The clarification path ends with `needs_clarification` instead.

## 6. Stage detail

### 6.1 Event typing

`process_message()` in `app/orchestration/workflow.py` checks ordered regular expressions and takes the first match:

1. `supplier_delay`: `delay|late|postpon`
2. `delivery_complaint`: `delivery|delivered|arriv`
3. `product_request`: `request|need|asking|pack`
4. `scheme_question`: `scheme|offer|discount`
5. `competitor_observation`: `competitor|nearby shop`

Only `supplier_delay` has a planning implementation. Other intents return an event-only mock result with the triggering phrase and a fixed uncertainty note.

Order matters. The demo text contains "delay", so it is classified as `supplier_delay` before any later rule can match.

### 6.2 Evidence extraction

For `supplier_delay`, three facts are extracted:

| Field | Pattern | Demo value | Exact span | Offsets |
|---|---|---|---|---|
| `supplier_id` | `\b(SUP-\d{3})\b` | `SUP-005` | `SUP-005` | 9 to 16 |
| `delay_days` | numeric or word duration followed by `day` or `days` and `delay` | `2` | `two-day` | 27 to 34 |
| `product` | matched catalogue label | `Cooking oil 1 L pouch` | `Cooking oil 1 L pouch` | 45 to 66 |

The delay evidence span is the first token of the matched phrase (`two-day`), not the full phrase `two-day delay`. This is deliberate: the duration token is the asserted fact; the word "delay" is the trigger. The extracted numeric value is normalized to `2`.

Every fact is created with `confidence="reported"`. The system never marks a supplier claim as verified.

### 6.3 Product resolution

`_resolve_product()` first tries an exact case-insensitive match of `product_name` plus `pack_description`. If no full label matches, it falls back to the bare category name.

Resolution succeeds only when all matches point to exactly one SKU. Consequences:

- `Cooking oil 1 L pouch` maps to `SKU-003` as a **catalogue inference**, not a fact stated by the source.
- Plain `Rice` matches both SKU-001 and SKU-002, so resolution fails. The workflow asks for clarification instead of choosing one.
- Plain `Cooking oil` matches both SKU-003 and SKU-004, so it also fails.
- A product with no catalogue match fails.

The resulting event records `inferences.catalogue_sku_id`, keeping the inference separate from `extracted_facts`.

### 6.4 Assumptions and unknowns

The happy path records three unknowns:

- Supplier-confirmed revised delivery date.
- Source-stated delayed quantity.
- Purchase-order reference.

The workflow never computes a revised date. It computes **scenario arrival dates** from the state's as-of date plus lead time, and labels them as planning estimates.

A key simulation assumption is that all 12 incoming SKU-003 litres are unavailable until the delayed arrival. At runtime the workflow takes `incoming_units` from inventory and passes it as `delayed_incoming_units`; the fixture records the same number under `assumptions.delayed_incoming_units`. This is an assumption, not an extracted fact, and it is visible in:

- `event.inferences.delayed_incoming_assumption`
- the inventory agent's `assumptions`
- the recommendation's `assumptions`

The planning horizon is the latest requested delivery date among affected orders, which is 2026-11-04. This is also an inference, recorded as `event.inferences.scenario_planning_horizon`.

### 6.5 Inventory analysis

`analyze_inventory()` in `app/agents/inventory.py` computes:

```text
available before delay = on_hand - reserved + incoming
immediately available  = on_hand - reserved + (incoming - delayed incoming)
```

For SKU-003:

```text
before delay = 62 - 6 + 12 = 68 litres
immediate    = 62 - 6 + (12 - 12) = 56 litres
```

The agent also reports whether the reorder point is reached. For this state it is not. The agent does not mutate inventory.

### 6.6 Order analysis

`analyze_orders()` in `app/agents/orders.py` selects open orders for the SKU and sorts them by `order_date` then `order_id`. All six demo orders have the same order date, so the order ID is the effective tie-breaker.

| Order | Retailer | Due date | Litres |
|---|---|---|---|
| ORD-0001 | RET-017 | 2026-11-02 | 17 |
| ORD-0006 | RET-019 | 2026-11-03 | 21 |
| ORD-0018 | RET-013 | 2026-11-02 | 9 |
| ORD-0019 | RET-019 | 2026-11-02 | 10 |
| ORD-0023 | RET-002 | 2026-11-02 | 27 |
| ORD-0028 | RET-001 | 2026-11-04 | 18 |
| **Total** | | | **102** |

### 6.7 Supplier options

Required units are:

```text
max(total requested - immediately available, 0)
= max(102 - 56, 0)
= 46 litres
```

`build_supplier_options()` considers every listed offer for SKU-003. It orders `max(required, MOQ)` units. For the original supplier under delay, it adds the reported delay to the listed lead time. It then checks capacity and whether the scenario arrival fits inside the planning horizon.

| Supplier | Unit cost | MOQ | Capacity | Lead days | Scenario arrival | Cost for 46 L | Feasible |
|---|---|---|---|---|---|---|---|
| SUP-002 | ₹106.01 | 10 | 54 | 2 | 2026-11-03 | ₹4,876.46 | Yes |
| SUP-003 | ₹102.35 | 5 | 51 | 3 | 2026-11-04 | ₹4,708.10 | Yes |
| SUP-005 (delayed) | ₹94.41 | 10 | 158 | 1 + 2 = 3 | 2026-11-04 | ₹4,342.86 | Yes |

All three are feasible. SUP-005 remains cheapest per unit, but its delay makes it arrive as late as SUP-003.

### 6.8 Candidate plans

`build_candidate_plans()` in `app/optimization/baseline.py` always creates a stock-only plan. It adds a supplier plan only when the option is feasible and its cash projection does not breach the buffer.

Each plan allocates stock first, in order sequence, then supplier units to the remaining quantities. Stock is assumed immediately usable, so only supplier-allocated units can be late. A unit is late when the scenario arrival date is after that order's requested delivery date.

For the selected supplier plan:

- Stock fulfils 56 litres across ORD-0001, ORD-0006, ORD-0018, and 9 of ORD-0019.
- Supplier fulfils 1 litre of ORD-0019, all 27 of ORD-0023, and all 18 of ORD-0028.
- With SUP-002 arriving 2026-11-03, the 1 + 27 = 28 litres due 2026-11-02 are late.
- The 18 litres due 2026-11-04 are on time.
- Total fulfilled: 102. Late: 28. Unmet: 0.

Candidate IDs are `stock-only`, `supplier-SUP-002`, `supplier-SUP-003`, and `supplier-SUP-005`.

### 6.9 Selection

`select_best_plan()` uses lexicographic ordering, not a weighted score:

```text
(unmet_units, late_units, scenario_arrival_date, total_cost_rupees, candidate_id)
```

Consequences:

1. Fulfilling demand outranks being on time.
2. Being on time outranks being cheap.
3. Earlier arrival wins before cost is considered.
4. Cost only breaks ties among otherwise equivalent plans.
5. Candidate ID makes the final tie-break deterministic.

The stock-only plan loses on unmet units: 46 unmet versus 0. SUP-002 beats SUP-003 and SUP-005 because it arrives on 2026-11-03 and limits lateness to 28 litres, while the others arrive on 2026-11-04 and make all 46 supplier-allocated litres late. SUP-002 is not the cheapest option; it is selected because lateness is prioritized above cost.

This is a policy choice, not an objective truth. Section 13.3 explains where to make the policy configurable or replace it with a formal optimizer.

### 6.10 Cash projection

`project_cash()` in `app/agents/cashflow.py` treats the procurement cost as an immediate outflow with no additional inflows. It rejects negative magnitudes and checks the minimum buffer.

For the selected plan:

```text
ending cash = 250,000.00 - 4,876.46 = 245,123.54
headroom    = 245,123.54 - 50,000.00 = 195,123.54
feasible    = true
```

Supplier payment terms exist in the supplier master but are not modeled. Treating the cost as immediate is conservative.

### 6.11 Independent verification

`verify_plan()` in `app/verification/checks.py` recomputes from the original state rather than trusting the plan. It checks:

- State version matches.
- Every allocation references a real order.
- Order SKU, requested quantity, and requested date match the state.
- Fulfilment split equals stock plus supplier.
- Fulfilled plus unmet equals requested.
- Late units equal supplier units when arrival is after the due date.
- No supplier allocation exists in a stock-only plan.
- Stock allocation does not exceed immediately available units.
- Supplier allocation does not exceed the option quantity.
- Arrival does not exceed the planning horizon.
- The offer exists and the unit cost matches the state.
- MOQ and capacity are respected.
- Total cost equals quantity times the state unit cost.
- Ending cash equals opening cash minus cost.
- Ending cash meets the minimum buffer.
- Plan totals equal the sum of allocation rows.

Any violation makes `valid` false. Violations are duplicated into the recommendation warnings, and the review status becomes `needs_clarification` instead of `pending_review`.

The demo returns `valid: true` with no violations.

### 6.12 Recommendation

`Recommendation` carries:

- A deterministic ID.
- The state version.
- A summary with quantity, supplier, fulfilment, lateness, and unmet units.
- Evidence references: the source message and the state version.
- Assumptions and warnings.
- `review_status="pending_review"`.
- `human_approval_required=true`.

The recommendation never includes an execution command, a purchase order, or a payment instruction.

## 7. Worked result

```text
Message:        Sri Venkateswara FMCG Supply reports a two-day delay for Cooking oil 1 L pouch
Supplier:       SUP-005 (resolved from the written trade name)
SKU:            SKU-003 (inference)
Inventory:      68 L before delay, 56 L immediately usable
Orders:         6 open, 102 L requested
Required:       46 L
Options:        SUP-002 46 L @ ₹106.01 = ₹4,876.46, arrival 2026-11-03
                SUP-003 46 L @ ₹102.35 = ₹4,708.10, arrival 2026-11-04
                SUP-005 46 L @ ₹94.41  = ₹4,342.86, arrival 2026-11-04
Selected:       supplier-SUP-002
Outcome:        102/102 fulfilled, 28 late, 0 unmet
Ending cash:    ₹245,123.54
Headroom:       ₹195,123.54
Verification:   valid
Review:         pending_review
```

## 8. Contracts and serialization

`app/schemas/contracts.py` is the shared boundary. The important properties are:

- `EvidenceFact` carries `evidence_span`, `span_start`, `span_end`, and `confidence`.
- `BusinessEvent` separates `extracted_facts`, `inferences`, and `uncertainties`.
- `AgentResult` carries `proposal`, `evidence_refs`, `assumptions`, and `warnings`.
- `SupplierOption` and `CandidatePlan` use `Decimal` for all money.
- `CashProjection` exposes ending cash, buffer, headroom, and feasibility.
- `VerificationResult` is a boolean plus machine-readable violation codes.
- `Recommendation` carries review state and human-approval requirement.

Pydantic serializes `Decimal` to a JSON string in `model_dump(mode="json")`. The API therefore returns values such as `"4876.46"` and `"245123.54"`. The dashboard converts these strings back to `Decimal` for display. This avoids binary floating-point drift between the calculation and the presentation.

IDs are deterministic:

```text
event_id          = "evt-" + sha256(message_id | text | state_version)[:12]
recommendation_id = "rec-" + sha256(event_id | candidate_id)[:12]
```

Repeating the same request produces the same IDs and the same ranking.

## 9. Entry points

### CLI

```powershell
python scripts\run_scenario.py --scenario SCN-003 --mode mock
```

- Loads the fixture.
- Validates the message contract.
- Calls the same workflow as the API.
- Prints the full JSON result.
- Exits 0 only when verification is valid.

### API

```powershell
uvicorn app.main:app --reload
```

- `GET /health` returns `{"status": "ok", "mode": "mock"}`.
- `POST /api/v1/messages/process` accepts `MessageSubmission` and returns the workflow result.
- A state-version mismatch returns HTTP 409.
- Missing or invalid synthetic state returns HTTP 500 with a safe message.

### Dashboard

```powershell
streamlit run app\dashboard\home.py
```

The dashboard shows six sections: evidence-linked event, operational impact, supplier and cash alternatives, selected plan, independent verification, and human review. Approve and reject buttons change only `st.session_state.review_status`. They do not call a write API, persist a decision, or execute an action.

## 10. Failure and edge paths

| Condition | Behavior |
|---|---|
| Missing supplier reference, delay duration, or unambiguous product | HTTP 200 with `event.status=needs_clarification`, empty candidate plans, null selected plan, recommendation status `needs_clarification` |
| Ambiguous product such as `Rice` | Same clarification path; no SKU is guessed |
| Product not in catalogue | Same clarification path |
| State version does not match the request | HTTP 409 from `StateVersionMismatch` |
| Missing or corrupt synthetic state | HTTP 500 from `StateLoadError` with a generic message |
| Invalid numeric value in a CSV | `StateLoadError`, HTTP 500 |
| Duplicate SKU, order, or supplier key | `StateLoadError` at load time |
| Supplier plan breaches the cash buffer | Supplier candidate is not added |
| State itself is below the minimum buffer | Stock-only plan remains, verification reports `minimum_cash_buffer_breached`, recommendation becomes `needs_clarification` |
| Forged or inconsistent candidate | Verifier returns specific violation codes and the recommendation is not marked reviewable |
| Unknown supplier in a candidate | `invalid_supplier_offer` violation |
| Supplier cost mismatch | `supplier_unit_cost_mismatch` and `candidate_cost_mismatch` violations |
| Repeated identical request | Identical IDs, ranking, and totals |

Clarification is a normal advisory outcome, not an HTTP error. The API distinguishes between "the message is insufficient" (200) and "the system cannot evaluate the request safely" (409 or 500).

## 11. Invariants and safety boundaries

These invariants must remain true in every future version:

1. Source text is stored verbatim and never rewritten.
2. A fact's evidence span must exist in the source and match its value.
3. A missing date, quantity, SKU, order ID, or PO reference is never fabricated.
4. Catalogue mapping is an inference, not a fact.
5. Scenario arrival dates are planning estimates, not supplier commitments.
6. All money is exact `Decimal` rupees.
7. A plan cannot allocate more stock or supplier units than are available.
8. A recommendation cannot be produced without successful verification.
9. A recommendation cannot execute a purchase, payment, stock change, price change, credit decision, or outbound message.
10. Human review is required and is not simulated by the API.
11. Synthetic and real data are never blended in one evaluation.
12. Secrets and real identifiable data are never committed.

## 12. Test coverage map

| Test file | What it protects |
|---|---|
| `tests/test_state.py` | Versioned load, exact rupee values, version mismatch rejection |
| `tests/test_agents.py` | Inventory and order impact, listed supplier offers with scenario delay, negative cash magnitude rejection |
| `tests/test_planning.py` | Deterministic supplier selection and verification, stock overallocation rejection, cash-buffer breach rejection |
| `tests/test_workflow_supplier_delay.py` | Complete golden path, determinism, ambiguous product clarification, repeatable CLI output |
| `tests/test_api.py` | Health, primary demo through HTTP, 409 on state-version mismatch |

Run the suite with:

```powershell
python -m pytest -q
```

## 13. Reuse for real AI and RAG

> The accepted intake design (open-world taxonomy, slot-filling, acknowledgement rules, triage and approval expiry) is specified in `docs/INTAKE_DESIGN.md`. This section remains the reference for what in the decision spine is reused unchanged.

### 13.1 Short answer

Yes, most of this code is reusable, but not the parts that pretend to understand language.

The reusable part is the **decision spine**: contracts, state loading, inventory and order math, supplier option construction, candidate ranking, independent verification, API boundary, dashboard, and tests. That spine does not care whether a fact came from a regex or an LLM, as long as the fact arrives in the same schema with valid evidence.

The parts that must change are:

- Regex event typing and extraction.
- The empty retrieval placeholder.
- Hardcoded scenario assumptions.
- The fixed `rules_mock` mode and the absence of a provider adapter.
- The lack of persistence, idempotency, and audit for real operations.

In one sentence: **AI can replace the intake layer, RAG can add cited policy context, and the deterministic verifier remains the authority.**

### 13.2 What stays unchanged

| Layer | File | Why it survives |
|---|---|---|
| Shared contracts | `app/schemas/contracts.py` | Already separates facts, inferences, assumptions, unknowns, plans, and verification |
| State loading and version gate | `app/state.py` | Real data can be loaded behind the same `BusinessState` shape |
| Inventory math | `app/agents/inventory.py` | Pure arithmetic over state |
| Order selection | `app/agents/orders.py` | Pure state query |
| Supplier options | `app/agents/supplier.py` | Pure enumeration and constraint checks |
| Cash projection | `app/agents/cashflow.py` | Exact `Decimal` arithmetic |
| Candidate generation and ranking | `app/optimization/baseline.py` | Deterministic and replaceable behind the same functions |
| Independent verification | `app/verification/checks.py` | The core trust boundary; should grow, not be discarded |
| Orchestration shape | `app/orchestration/workflow.py` | The stage sequence remains valid |
| API boundary | `app/main.py` | Same request and response contract |
| Dashboard | `app/dashboard/home.py` | Same six-section review flow |
| Regression tests | `tests/` | Golden values and failure cases remain valid |

The key compatibility condition is that any new extractor must emit the existing `EvidenceFact`, `BusinessEvent`, and `MessageSubmission` contracts. If it does, everything downstream works unchanged.

### 13.3 What must be replaced or extended

| Current component | Replacement or extension | Reason |
|---|---|---|
| `RULES` regex event typing | LLM classifier or hybrid rules-plus-LLM classifier with deterministic fallback | Real messages are multilingual, indirect, and mixed-intent |
| `DELAY_PATTERN` and supplier regex | Schema-constrained LLM extraction | Real phrasing varies; regex will not generalize |
| `_resolve_product()` | LLM candidate generation plus authoritative catalogue lookup | The model may propose labels; only the catalogue may assign SKU IDs |
| Fixed `mode="rules_mock"` | Provider adapter selected by configuration | Keep mock mode for tests and offline demos |
| Empty `app/rag/retrieval.py` | Real retriever with source metadata and citations | RAG needs passages, versions, and permissions, not just text |
| Runtime use of all incoming units as delayed | Explicit `ScenarioConfig` loaded from the fixture or scenario service | Simulation assumptions must be data, not hidden code behavior |
| Fixed ranking tuple | Configurable policy or OR-Tools model behind the same interface | Real trade-offs between lateness, cost, and service level need explicit weights or constraints |
| Immediate-cash treatment | Payment-term-aware cash flow | Supplier terms and retailer receipts affect liquidity |
| In-memory result only | Repository, idempotency key, audit log, optimistic concurrency on `state_version` | Real operations need traceability and safe retries |
| Session-only approval | Persisted human decision plus an outbox for approved actions | Approval must be attributable, and actions must be executed separately and safely |
| Current verifier | Extended verifier for AI output validity and retrieved-source grounding | The verifier must check the new inputs, not just the old arithmetic |

### 13.4 Target architecture with LLM and RAG

```text
Message
  -> LLM structured extraction (JSON schema, temperature 0)
  -> schema validation
  -> evidence-span validation (text[start:end] == evidence_span)
  -> catalogue authority check (SKU must exist; ambiguous -> clarify)
  -> deterministic specialist agents
  -> RAG retrieval over approved policies and SOPs
  -> candidate generation and ranking
  -> independent verifier (facts, arithmetic, constraints, citations)
  -> recommendation with evidence and document citations
  -> human review
  -> optional approved-action outbox
```

The LLM never computes inventory, cost, cash, or feasibility. RAG never supplies business state. The state remains the sole source of quantities, prices, and balances.

### 13.5 LLM extraction contract

Define a strict JSON schema, for example:

```json
{
  "event_type": "supplier_delay",
  "supplier_id": "SUP-005",
  "product_text": "Cooking oil 1 L pouch",
  "sku_id": null,
  "delay_days": 2,
  "delayed_quantity": null,
  "revised_date": null,
  "po_reference": null,
  "evidence": [
    {"field": "supplier_id", "value": "SUP-005", "span": "SUP-005"},
    {"field": "delay_days", "value": "2", "span": "two-day"},
    {"field": "product", "value": "Cooking oil 1 L pouch", "span": "Cooking oil 1 L pouch"}
  ]
}
```

Validation rules:

1. Every evidence span must be an exact substring of the source; the server computes offsets itself.
2. `sku_id` must be null or a real catalogue ID. The model may not invent SKU IDs.
3. If the product label maps to more than one SKU, return null and request clarification.
4. `revised_date` must be null unless the source states it. "Two-day delay" does not imply a date.
5. `delayed_quantity` must be null unless the source states it.
6. Numbers must have explicit units where the domain requires them.
7. Unknown fields are rejected or ignored explicitly, never silently merged.
8. The message is treated as data, not instructions. Prompt-injection text inside a supplier message must not change system behavior.
9. Low confidence or schema failure falls back to the rules extractor or a clarification response, not to a guess.
10. Extraction output is logged with provider, model, prompt version, and validation result, without logging sensitive source text in plaintext beyond the approved retention policy.

The LLM should be evaluated on exact-span match, field precision and recall, and clarification behavior on ambiguous inputs, not just fluent output.

### 13.6 RAG contract

`app/rag/retrieval.py` currently returns an empty list. A real implementation should provide:

```python
def retrieve(query: str, top_k: int = 5) -> list[dict]:
    ...
```

Each result should include:

- `doc_id`
- `chunk_id`
- `text`
- `source_type`
- `version` or `effective_date`
- `sensitivity`
- `score`
- `span_start` and `span_end` where applicable

Rules:

1. Index only approved or synthetic documents. Never index unapproved pilot data by accident.
2. Filter by tenant, role, and sensitivity before retrieval, not after generation.
3. Every retrieved claim used in a recommendation must carry a citation.
4. If no supporting passage is retrieved, say so; do not fill the gap with model knowledge.
5. Retrieved text is data, not instruction. It cannot override constraints or safety rules.
6. Keep document versions so a past recommendation can be reproduced.
7. Separate "policy says" from "state says" in the output.

In SCN-003, RAG is optional. The supplier-delay arithmetic does not need document retrieval. RAG becomes useful for questions such as which escalation policy applies, what the approved substitution rule is, or how a delay should be communicated under the current SOP. Those citations belong beside the recommendation, not inside the arithmetic.

### 13.7 Verification gates for AI output

The verifier should gain a pre-plan gate and keep its post-plan gate:

**Pre-plan gates**

- Source consent and source type are allowed.
- Extracted JSON validates against the schema.
- Every evidence span is an exact substring.
- Every enum value is allowed.
- Every SKU exists in the catalogue.
- No date, quantity, or reference is populated without evidence.
- Ambiguity produces clarification, not a guess.

**Post-plan gates**

- All current arithmetic and constraint checks.
- Every RAG-derived claim has a valid citation.
- No recommendation cites a document that was not retrieved for this request.
- The final summary contains no number that is absent from the verified plan.

If any gate fails, the result is clarification or rejection, not a best-effort recommendation.

### 13.8 Migration sequence

A low-risk path from the current demo to real AI and RAG:

1. **Make assumptions explicit.** Add a `ScenarioConfig` model and load delayed units, horizon, original supplier, and cost timing from the fixture. No AI yet; this removes hidden behavior.
2. **Introduce an extraction interface.** Add a provider protocol with a mock implementation that wraps the current regex logic. Keep all tests green.
3. **Add an LLM implementation behind the same interface.** Constrain it with JSON schema, temperature 0, and the pre-plan gates. Compare it against the mock on a labeled set before enabling it by default.
4. **Add retrieval with citations.** Implement `retrieve()` against approved documents and require citations for policy claims. Keep SCN-003 arithmetic unchanged.
5. **Make ranking policy explicit.** Move the tuple into configuration or an OR-Tools model, then verify that the SCN-003 result is explainable under the chosen policy.
6. **Add persistence and audit.** Store requests, extraction outputs, plans, verification results, and human decisions with idempotency keys and state-version concurrency checks.
7. **Add an approved-action outbox.** Only after a human approves, and only for explicitly authorized action types, with separate credentials and audit. This remains outside the capstone demo.
8. **Expand evaluation.** Track extraction accuracy, span exactness, clarification rate, plan feasibility, verifier catch rate, citation groundedness, and end-to-end scenario pass rate. Keep synthetic and real results separate.

Steps 1 and 2 are worth doing even if the team never enables an LLM: they turn hidden assumptions into data and make the current rules replaceable.

### 13.9 What is not reusable

Be explicit about the gaps:

- The message-specific regexes are demo scaffolding, not a production NLU layer.
- The empty retriever is a contract placeholder, not RAG.
- The fixed ranking is a policy choice, not a general optimizer.
- The fixture is documentation, not runtime configuration.
- The dashboard approval is a UI state, not an audited decision.
- The current state loader assumes local synthetic files, not a transactional system of record.
- The current code has no authentication, authorization, tenant isolation, rate limiting, or PII handling.
- The current verifier checks arithmetic and constraints, not the validity of model output or the grounding of citations.

None of these gaps invalidate the design. They define the boundary between the reusable decision spine and the production intake and integration layers that still need to be built.

## 14. Known limitations of this slice

- One event type has a planning implementation; the others are event-only.
- One SKU family per message.
- Product resolution is label-based and deliberately fails on category ambiguity.
- All incoming units for the affected SKU are treated as delayed; partial shipment delay is not modeled.
- Stock is assumed immediately usable and never late.
- Supplier cost is an immediate outflow; payment terms are ignored.
- Quantity is `max(required, MOQ)`, so a small need can trigger a larger order.
- Ranking prioritizes unmet units, then lateness, then arrival, then cost; this is not configurable.
- No substitution between packs or products.
- No multi-supplier split, no partial shipments, no transportation constraints.
- No persistence, authentication, or audit.
- No LLM, embeddings, or retrieval yet.
- Synthetic data only.

## 15. File map

| Path | Responsibility |
|---|---|
| `app/schemas/contracts.py` | Shared Pydantic contracts |
| `app/state.py` | Versioned synthetic state loading |
| `app/agents/inventory.py` | Availability and reorder analysis |
| `app/agents/orders.py` | Affected open orders |
| `app/agents/supplier.py` | Supplier option enumeration and constraints |
| `app/agents/cashflow.py` | Exact cash projection |
| `app/optimization/baseline.py` | FIFO allocation, candidate plans, deterministic ranking |
| `app/verification/checks.py` | Independent plan verification |
| `app/orchestration/workflow.py` | SCN-003 vertical slice and clarification path |
| `app/main.py` | FastAPI entry point |
| `app/dashboard/home.py` | Streamlit review dashboard |
| `app/rag/retrieval.py` | Retrieval interface placeholder |
| `scripts/run_scenario.py` | Repeatable CLI runner |
| `data/synthetic/scenario_fixtures/SCN-003.json` | Canonical demo input and assumptions |
| `tests/` | Golden path, determinism, ambiguity, verification, API tests |
