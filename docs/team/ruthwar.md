# Ruthwar — Architecture, orchestration and API

**Master-plan role:** Member 1. **Team role:** kickoff lead and integration coordinator. Capstone-only scope.

## Own

- Shared contracts (`Message`, `BusinessEvent`, `BusinessState`, `AgentResult`, `Recommendation`) with stable IDs, state version, evidence, uncertainty and review status.
- FastAPI routes, request validation, workflow routing, provider-independent model adapter, structured output validation, timeouts/retries and run traces.
- Integration plan and API-first mock end-to-end path; keep external model calls optional.

## Kickoff / first slice

Lead the scope and scenario decision, publish the contract draft, assign interface dependencies, and show a submitted message becoming an event in mock mode. Agree PR/review practice and maintain `docs/DECISIONS.md`.

## Handoffs and done evidence

Agree inventory/order/supplier outputs with Saurabh, Rajesh and Rohit; give Ranjit workflow outputs for optimization/dashboard; agree message evidence and uncertainty with Varsha. Done when a deterministic request traverses the shared workflow, invalid output/failure is represented safely, and another member can run it from the README.

## Shared obligations

Contribute one normal and one failure/edge scenario, sample input/output, documentation, peer review and demo explanation. Never put keys in source control; no action executes without human approval.
