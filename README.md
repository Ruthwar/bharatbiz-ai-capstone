# BharatBiz AI Capstone

Academic capstone prototype for evidence-backed business conversation intelligence and constraint-checked operational decision support for FMCG distributors. This repository is for research and demonstration only; it is not a commercial product.

## Scope

The MVP connects permitted message/visit-note intake to synthetic operational state (inventory, retailer orders, suppliers and cash), produces evidence-linked events, and supports deterministic analysis and human-reviewed recommendations. All impactful actions remain human-approved. No live ERP/WhatsApp integration or automatic purchasing, payment, pricing, credit or retailer messaging is in scope.

## Quick start

Requires Python 3.11+ and Git.

```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python scripts\generate_synthetic_data.py
uvicorn app.main:app --reload
```

Open `/docs` for the API. The starter workflow is deterministic mock mode and requires no model key. Copy `.env.example` to `.env` only if needed; never commit secrets.

## Primary demo: SCN-003 supplier delay

The first vertical slice processes a two-day supplier delay for Cooking oil 1 L pouch. It preserves exact evidence and unknowns, calculates inventory/order impact, compares supplier and cash alternatives, selects a deterministic plan, independently verifies it, and leaves the recommendation pending human review.

Run the repeatable no-key scenario:

```powershell
python scripts\run_scenario.py --scenario SCN-003 --mode mock
```

Start the API in one terminal:

```powershell
uvicorn app.main:app --reload
```

Start Streamlit in a second terminal:

```powershell
streamlit run app\dashboard\home.py
```

Select **Run SCN-003** in the dashboard. Approve/reject changes only the demo session; no purchase, payment, stock update, or outbound message is executed.

Install test dependencies and run the regression suite:

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

The canonical input and explicit simulation assumptions are in `data/synthetic/scenario_fixtures/SCN-003.json`. The end-to-end design, verification contract, and reuse plan for LLM/RAG are in `docs/SCN-003_DESIGN.md`.

## Repository map

- `app/schemas/` shared contracts
- `app/agents/` specialist analysis modules
- `app/orchestration/` deterministic mock workflow and SCN-003 vertical slice
- `app/optimization/` deterministic allocation and candidate-plan baseline
- `app/verification/` independent plan checks
- `app/rag/` retrieval interface placeholder
- `app/dashboard/` Streamlit SCN-003 decision and evidence display
- `data/synthetic/` generated synthetic CSV/JSONL and data dictionary
- `data/knowledge_docs/` approved/synthetic reference documents only
- `data/pilot_deidentified/` reserved for authorized, de-identified pilot samples; empty by default
- `data/labels/` annotation guide and evaluation labels
- `docs/` kickoff, team ownership and individual role briefs

## Data and provenance

Generate the new plan-aligned pack with `python scripts/generate_synthetic_data.py --seed 20261105`. The script is deterministic for a fixed seed and labels every row synthetic. It creates 1,000 language examples and coherent, small operational tables for repeatable scenario work. The former v1 data pack remains in the parent folder as a historical reference; it is not the source of truth for this repo.

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
