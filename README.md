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

## Repository map

- `app/schemas/` shared contracts
- `app/agents/` specialist analysis modules
- `app/orchestration/` mock workflow
- `app/optimization/` initial allocation baseline
- `app/verification/` independent checks
- `app/rag/` retrieval interface placeholder
- `app/dashboard/` Streamlit entry point placeholder
- `data/synthetic/` generated synthetic CSV/JSONL and data dictionary
- `data/knowledge_docs/` approved/synthetic reference documents only
- `data/pilot_deidentified/` reserved for authorized, de-identified pilot samples; empty by default
- `data/labels/` annotation guide and evaluation labels
- `docs/` kickoff, team ownership and individual role briefs

## Data and provenance

Generate the new plan-aligned pack with `python scripts/generate_synthetic_data.py --seed 20261105`. The script is deterministic for a fixed seed and labels every row synthetic. It creates 1,000 language examples and coherent, small operational tables for repeatable scenario work. The former v1 data pack remains in the parent folder as a historical reference; it is not the source of truth for this repo.

Keep original text separate from extracted facts and inferences. Facts must include exact evidence spans; unknown dates, quantities, SKUs, order references and identities stay unknown. Use ISO dates, explicit units, integer paise for money and stable IDs.

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
