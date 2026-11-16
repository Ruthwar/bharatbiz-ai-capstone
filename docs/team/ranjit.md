# Ranjit — Planning, optimization, verification, dashboard and evaluation

**Master-plan role:** Member 6. Capstone-only scope.

## Own

- Negotiation interface and candidate-plan representation.
- OR-Tools optimization baseline with explicit service, supplier, lead-time, capacity and cash constraints; explain infeasibility.
- Independent plan verifier, Streamlit decision/evidence dashboard, baseline comparison and repeatable evaluation scripts/report.

## Kickoff / first slice

Agree the optimization objective and hard constraints with Ruthwar, Saurabh, Rajesh and Rohit; define the verifier input/output separately from optimizer internals; sketch the supplier-delay demo and key metrics.

## Handoffs and done evidence

Consume stable BusinessState and specialist proposals; return candidate plan, tradeoffs, warnings, constraint checks and human-review state. Done when a feasible plan or explicit infeasibility is displayed, and a deliberately bad plan is rejected by independent checks.

## Shared obligations

Add one feasible and one infeasible/constraint-violation scenario, sample input/output, documentation, peer review and demo explanation. Compare approaches on identical data; report evidence and limitations without assuming coordinated agents win.
