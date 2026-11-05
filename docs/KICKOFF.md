# BharatBiz AI capstone kickoff

**Purpose:** start the unified academic capstone described in `BharatBiz_AI_Master_Project_Plan_Formatted.docx`. The project is for academic research and demonstration only, with no commercial launch or production claims.

## 1. Open the kickoff meeting (60–75 minutes)

1. Ruthwar explains the user problem and the project promise: connect permitted business conversations to operational records and produce evidence-backed, constraint-checked options for human review.
2. Read the agreed MVP aloud: message intake and understanding; retailer/sales/supplier events; simulated inventory, orders, suppliers and cash; coordinated workflow; deterministic optimizer and verifier; basic RAG; Streamlit dashboard; mock mode; reproducible evaluation.
3. Confirm the boundary: no automated purchases/payments/pricing/credit decisions, no unreviewed retailer-facing responses, no private-message scraping, no live ERP or official WhatsApp integration in the MVP.
4. Walk through the supplier-delay demo: message → evidence-linked event → related stock/orders → supplier and cash options → optimizer → independent checks → human review. Select one secondary retailer/market-intelligence scenario.
5. Confirm shared contracts, repository access, module ownership and integration points. Use the individual briefs in `docs/team/` to begin work.
6. Record decisions and owners in `docs/DECISIONS.md`; assign a due date to every unresolved decision.

## 2. Decisions to close at kickoff

- Primary demo: recommended supplier delay; secondary demo: retailer complaint or smaller-pack request.
- Shared `Message`, `BusinessEvent`, `BusinessState`, `AgentResult` and `Recommendation` contracts, including state version, evidence, uncertainty and review status.
- Python 3.11+, FastAPI/Pydantic, LangGraph, SQLite for initial demo, OR-Tools baseline, Streamlit, and approved provider adapter. Keep the first workflow usable with no model API.
- Dataset files and units from `data/synthetic/`; exact seed and generation version recorded with each evaluation run.
- Whether a permissioned pilot is feasible. Do not block engineering while arranging it.
- GitHub host/organization and repository visibility, branch protections and access for all six members.
- Meeting rhythm, review partner, issue tracker and how blockers are raised.

## 3. First 48 hours (4–6 Nov plan window)

- Everyone clones the repo, creates the Python environment, generates the data, starts the API and makes one small branch/commit.
- Ruthwar publishes shared schema draft and integration boundaries; each owner comments before interfaces are frozen.
- Dataset lead reviews tables, labels and coverage; team agrees how old v1 data will be treated (historical reference, not current baseline).
- Member owners create an issue list with a first working slice and sample input/output.
- Agree primary and secondary scenarios and define the expected human-reviewed output.
- Decide pilot permission approach and prepare interview/consent materials only if interviews are actually planned.

## 4. Working rhythm

Daily 10–15 minute check-in: yesterday's demonstrable result, today's target, blocker. Push small increments, integrate continuously, review shared contract changes together, and keep mock mode available. Each member supplies one normal scenario and one missing-data/failure case. Run the project checks before merging according to the team’s agreed workflow.

## 5. Capstone deliverables

- Reproducible synthetic operational/message dataset, with provenance and fixed scenarios.
- Working API and mock end-to-end workflow; specialist modules; RAG evidence retrieval; optimizer plus independent verifier; dashboard and human review state.
- Comparison of rules-only, single-model where permitted, independent specialists, fixed workflow and adaptive workflow on the same held-out scenarios.
- Report quality and operational metrics, latency/cost where model use occurs, limitations and synthetic/real sample separation.
- Architecture, setup instructions, demo script, reproducibility notes and presentation by submission target 27 Nov 2026; final presentation 5 Dec 2026.

## 6. Kickoff output checklist

- [ ] Scope, safety boundaries and two demo scenarios recorded
- [ ] Shared contracts and owners agreed
- [ ] GitHub destination/access and collaboration rules agreed
- [ ] All members can run the starter repo and synthetic-data generator
- [ ] One mock message produces an event with evidence and uncertainty
- [ ] Dataset schema, seed/version and evaluation split agreed
- [ ] Pilot decision, consent/de-identification plan, or explicit “simulation only” decision recorded
- [ ] Decision log and first issues assigned by name

## How to initiate today

Ruthwar should schedule the team kickoff, circulate this guide and each member’s brief, and ask everyone to arrive having read the master plan sections on scope, architecture, ownership, roadmap and evaluation. Start by agreeing the supplier-delay demo and shared contracts; then have all six members run the same starter command and take ownership of the first 4–6 Nov exit checkpoint. Keep the meeting’s decisions and any deviations in the log; the master plan remains the scope baseline unless the team records a deliberate change.
