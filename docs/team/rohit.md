# Rohit — Supplier and cash-flow analysis

**Master-plan role:** Member 4. Capstone-only scope.

## Own

- Supplier comparison: price, MOQ, capacity, lead time and payment terms.
- Supplier update extraction and linkage only when a reliable reference is stated.
- Cash projection, available spending and minimum cash buffer, using exact `Decimal` rupee calculations with two decimal places.

## Kickoff / first slice

Review `suppliers.csv`, `supplier_products.csv` and `cash_ledger.csv`; state the currency/unit convention and demonstrate a delayed supplier or liquidity case with feasible/infeasible result.

## Handoffs and done evidence

Use inventory/order impacts from Saurabh/Rajesh and provide constraints to Ranjith’s optimizer/verifier; preserve evidence and unknown commitment dates through Ruthwar’s contracts. Done when MOQ, capacity, lead-time and cash checks are deterministic and traceable.

## Shared obligations

Add one feasible and one infeasible/unknown-date case, sample input/output, documentation, peer review and demo explanation. Never let a model decide arithmetic or supplier commitment facts.
