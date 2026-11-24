# BharatBiz AI Capstone

Academic capstone prototype for evidence-backed business conversation intelligence and constraint-checked operational decision support for FMCG distributors. This repository is for research and demonstration only; it is not a commercial product.

## Scope

The MVP connects permitted message/visit-note intake to synthetic operational state (inventory, retailer orders, suppliers and cash), produces evidence-linked events, and supports deterministic analysis and human-reviewed recommendations. All impactful actions remain human-approved. No live ERP/WhatsApp integration or automatic purchasing, payment, pricing, credit or retailer messaging is in scope.

## Quick start

Requires Python 3.11+ and Git. A shareable setup and demo guide for the team is in [`docs/QUICKSTART.md`](docs/QUICKSTART.md).

```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python scripts\generate_synthetic_data.py
uvicorn app.main:app --reload
```

Open `/docs` for the API. The starter workflow is deterministic mock mode and requires no model key. Copy `.env.example` to `.env` only if needed; never commit secrets.

## Scenario suite

Fifteen explicit fixtures run through one scenario registry and immutable overlay contract. Operational scenarios use the same deterministic allocator, candidate ranking, visible exclusions, dated cash schedules and independent verifier. Case, market and advisory scenarios produce reviewable evidence without inventing an allocation plan or operational action. Three advisory scenarios compare precomputed outcomes and show why each alternative loses: dispatch planning (SCN-015) enumerates every non-split load plan, credit review (SCN-010) compares holding the order, pausing existing orders and accepting it, and batch recall (SCN-013) compares quarantine with release. In policy-grounded mode the model must confirm a supplied outcome with the governing citation (POL-SVC-009, POL-LIQ-007 or POL-STK-007 respectively) or abstain explicitly.

| Scenario | Focus | Expected review outcome |
| --- | --- | --- |
| SCN-001 | Normal day | Stock-only fulfilment |
| SCN-002 | Demand spike | Per-order ceiling rounding and procurement comparison |
| SCN-003 | Supplier delay | Canonical SUP-002 plan with 28 late units |
| SCN-004 | Limited cash and delayed receipt | Stock-only actual view plus on-time-receipt counterfactual |
| SCN-005 | Stock discrepancy | Book stock preserved beside the unverified physical count |
| SCN-006 | Retailer complaint | Order-reference clarification before case review |
| SCN-007 | Competitor observation | Deduplicated reports and distinct-reporter corroboration |
| SCN-008 | Combined disruption | Composed demand, delay and cash overlays with counterfactual |
| SCN-009 | Smaller-pack request | Aggregated unverified signal; no assortment change |
| SCN-010 | Overdue retailer with new order | Credit exposure above limit; hold, pause or accept compared; POL-LIQ-007 citation or abstention |
| SCN-011 | Scheme claim mismatch | Claim differs from the approved scheme register |
| SCN-012 | Short and damaged delivery | Delivery variance with a supplier claim candidate |
| SCN-013 | Batch recall and quality hold | Quarantine versus release compared; POL-STK-007 citation or abstention |
| SCN-014 | Short-dated stock and return window | Return eligibility inside the supplier window |
| SCN-015 | Dispatch under vehicle capacity | All feasible load plans compared; service-best plan with deferred order |

Run any scenario without a model key, or persist its review outcome in SQLite:

```powershell
python scripts\run_scenario.py --scenario SCN-003 --mode mock
python scripts\run_scenario.py --scenario SCN-007 --mode mock --persist-review
python scripts\evaluate_scenarios.py
```

The evaluator checks every fixture expectation and returns a nonzero exit code on any mismatch. The API exposes `GET /api/v1/scenarios` and `POST /api/v1/scenarios/{scenario_id}/run`; the run body accepts `{"persist_review": true}` and `{"decision_mode": "deterministic"}` by default or `{"decision_mode": "policy_grounded_llm"}` for grounded selection. Policy-grounded results either cite the rules behind a supplied option or record an explicit abstention; deterministic results never call the model.

Start the API and operations console in separate terminals:

```powershell
uvicorn app.main:app --reload
streamlit run app\dashboard\chat.py
```

Open **Scenario lab** to run any fixture and inspect alternatives, exclusions, counterfactuals, evidence and unknowns. **Decision desk** handles operational, complaint and market-signal reviews. **Retail desk** adds priority fulfilment analysis, durable cases, reply drafts, retailer history and market observations. Approval changes only demo/review state; no purchase, payment, stock update, assortment change or substantive outbound message is executed.

Install test dependencies and run the regression suite:

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

The canonical SCN-003 input and assumptions remain in `data/synthetic/scenario_fixtures/SCN-003.json`; its original design is in `docs/SCN-003_DESIGN.md`. Scenario fixtures are explicit simulation inputs and do not modify the base synthetic CSV state. The GitHub Actions workflow runs both pytest and the scenario evaluator.

## Open-ended message intake

`POST /api/v1/inbound` accepts a free-form message from a retailer, supplier or sales visit. It always returns a template receipt, may ask one question to complete required details, and then routes the event to a handler or to human triage. The design is specified in `docs/INTAKE_DESIGN.md`.

```powershell
uvicorn app.main:app --reload
streamlit run app\dashboard\chat.py
```

The chat page has an intake tab and a review queue. Selecting a sender in the UI simulates channel identity; a real channel derives it from the authenticated account. Receipt and completion acknowledgements are the only automated outbound text. No action executes without human approval.

**Demo examples** in Intake controls cover all fifteen fixtures. **Load editable example** fills the sender, language, conversation and message without submitting it, so the normal intake and clarification flow can be demonstrated. **Run full scenario** applies every fixture overlay and opens the canonical decision in Scenario lab without adding it to the review queue. Plain intake processes only the visible message; it does not reproduce scenario-only demand, cash, delay or stock overlays.

Model extraction is optional. With `LLM_PROVIDER=none` (the default) the deterministic rules extractor is used. To enable a provider, copy `.env.example` to `.env` (the app loads it automatically) and set `LLM_PROVIDER`, `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY`, and `LLM_CA_BUNDLE` if the endpoint uses a private CA. Verify the connection with `python scripts/check_llm.py`. Never commit `.env`; extraction output is validated against the schema, exact evidence spans and the product catalogue, and falls back to rules on failure.

## Model observability

**LLM observability** in the dashboard shows a local trace store at `data/runtime/traces.sqlite3` (override with `BHARATBIZ_TRACE_DB`). A scenario run, inbound message or evaluation job opens one trace; every model generation, retrieval call and rules fallback inside it becomes a span with latency, gateway-reported tokens, status and the ids the application used. `GET /api/v1/observability` returns the summary and runs, and `GET /api/v1/observability/traces/{trace_id}` returns one run's spans. Prompts and message bodies are not stored, and cost is not estimated unless `BHARATBIZ_TRACE_COST_PER_1K_TOKENS` is set. Export to Langfuse is opt-in and off by default (`BHARATBIZ_TRACE_EXPORT=langfuse` plus `LANGFUSE_HOST`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`); the ingestion hook has not been verified against a live instance. Deterministic rules extraction with no persisted review makes no model or retrieval call, so it records no span.

## Retail operations

Completed retailer and sales-visit intake persists interactions, cases, drafts and market observations in `data/runtime/retail.sqlite3`. Clarification rounds, duplicate deliveries, direct scenario runs and failed writes do not create a false dedup success. The bundled retail write is one SQLite transaction and is idempotent by event ID.

- **Priority fulfilment:** `GET /api/v1/retail/fulfilment` ranks open orders by order priority, requested delivery date, retailer service priority, order date and order ID. It is an additive analytical view; SCN-003 retains its first-come planner. Incompatible units are never converted.
- **Cases:** `GET /api/v1/retail/cases`, `GET /api/v1/retail/cases/{case_id}` and `PATCH /api/v1/retail/cases/{case_id}` support repeat-complaint linking, assignment, priority, activity history and guarded lifecycle transitions. Resolution requires a staff note.
- **Replies:** `GET /api/v1/retail/drafts` plus `/review` and `/mark-sent` under `/api/v1/retail/drafts/{draft_id}` provide deterministic English, Hinglish and Hindi acknowledgement drafts. Edits are checked for money, dates, commitments, causes, substitutes, questions and unsupported numbers. Approval is one-time and does not send or resolve; marking sent only records a manual staff action.
- **Retailers and market:** `GET /api/v1/retail/retailers/{retailer_id}` combines order history, priority allocation, cases and recurring issues. `GET /api/v1/retail/market-signals` groups observations by signal, subject, competitor, product, offer and area. Only stable non-empty reporter IDs count as corroboration; all signals remain unverified.
- **Indicative availability:** product requests show current base-unit stock and open-order allocation where a catalogue match exists. They do not confirm an order, reserve stock or include incoming supply.

Use `python scripts/reset_demo.py` to clear the review ledger, retail runtime store and local model traces. Runtime databases are excluded by `.gitignore`; override the retail path with `BHARATBIZ_RETAIL_DB` and the trace path with `BHARATBIZ_TRACE_DB` when needed.

## Repository map

- `app/schemas/` shared contracts
- `app/agents/` specialist analysis modules
- `app/extraction/` extraction interface: rules and LLM adapters plus pre-plan validation gates
- `app/channels/` channel adapters (demo chat; WhatsApp would normalise into the same contract)
- `app/orchestration/` LangGraph inbound graph (dedup, intake, slot gate, review queue), decision graph (understand, plan, verify, finalize), taxonomy, slot specs and intent router
- `app/scenarios/` fixture registry and validation, immutable operational overlays, complaint/market handlers and shared execution service
- `app/optimization/` deterministic allocation, candidate ranking and visible exclusion reasons
- `app/verification/` independent reconstruction and plan checks
- `app/store/` SQLite ledger for dedup, intakes and reviews, plus atomic durable retail cases, drafts, interactions and observations; reset with `python scripts/reset_demo.py`
- `app/rag/` corpus loader and SQLite FTS5 citation retriever over the approved reference documents
- `app/observability/` local SQLite trace store, API summary, and optional Langfuse exporter
- `app/evaluation/` frozen RAG and held-out extraction evaluation jobs
- `app/dashboard/` Streamlit operations console with overview, intake, scenario lab, decision desk, retail desk, operations data, evaluation, LLM observability and knowledge search
- `data/synthetic/` generated synthetic CSV/JSONL and data dictionary
- `data/knowledge_docs/` 33 approved reference documents (30 synthetic policies, SOPs, supplier terms and case notes, 3 cited regulatory extracts), plus `manifest.json`
- `data/eval/` golden retrieval queries, held-out extraction examples and evaluation labels kept separate from tuning data
- `data/pilot_deidentified/` reserved for authorized, de-identified pilot samples; empty by default
- `data/labels/` annotation guide and evaluation labels
- `docs/` kickoff, team ownership and individual role briefs

## Data and provenance

Generate the new plan-aligned pack with `python scripts/generate_synthetic_data.py --seed 20261105 --as-of 2026-11-23`. The script is deterministic for a fixed seed and labels every row synthetic. It creates 1,000 language examples and coherent, small operational tables for repeatable scenario work. The former v1 data pack remains in the parent folder as a historical reference; it is not the source of truth for this repo.

The knowledge corpus is curated, not generated. Rebuild its index and manifest with `python scripts/build_rag_index.py` after any edit, and measure retrieval with `python scripts/eval_rag.py` (40 golden queries, recall@k and a term-frequency baseline). Sources, licences and retrieval dates are recorded in `docs/RAG_CORPUS_SOURCES.md`; the measured results and known failures are in `docs/RAG_EVALUATION.md`. The review card cites up to three sections with document id, effective date, verbatim quote and licence. Retrieval supplies text, never quantities, prices or dates.

Keep original text separate from extracted facts and inferences. Facts must include exact evidence spans; unknown dates, quantities, SKUs, order references and identities stay unknown. Use ISO dates, explicit units, exact `Decimal` rupee values with two decimal places for money and stable IDs.

## Team workflow

Agree shared schemas before parallel module work. Make small commits on feature branches, open pull requests, request one peer review, and merge to `main` only after the team’s agreed checks pass. Each module owner contributes a normal example, an edge case, a sample input/output and a short README note. Integrate continuously.

## Research integrity and safe use

Synthetic data is fictional and must be described as such. Real examples require informed permission, minimum collection, de-identification, restricted access, retention/deletion notes and a suitable basis before any external model processing. Keep real and synthetic evaluation results separate. Recommendations are advisory and require a human reviewer.

## Milestone anchors

- 4–6 Nov 2026: scope, repository, environment, shared schemas and one mock request
- 7–10 Nov: individual module demonstrations and data/interview preparation
- 11–18 Nov: integrated workflow, RAG, optimizer and verifier
- 19–24 Nov: dashboard, failure cases and repeatable evaluation
- 25–27 Nov: report and submission package; 5 Dec: final presentation

See `docs/KICKOFF.md` and the named briefs in `docs/team/`.
The authoritative source plan is copied to `docs/master-plan/` for every clone.
