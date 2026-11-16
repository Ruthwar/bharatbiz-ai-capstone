# Saurabh — Inventory and demand analysis

**Master-plan role:** Member 2. Capstone-only scope.

## Own

- Inventory position, reserved/incoming quantities, reorder and shortage indicators, simple demand baseline, and expiry/capacity checks where simulated data supports them.
- Explicit units and SKU relationships; deterministic arithmetic and timestamp/state-version assumptions.
- Support mapping a stated product/request to a catalogue item only when evidence supports it; otherwise return unresolved.

## Kickoff / first slice

Review `data/synthetic/products.csv` and `inventory.csv`; propose the input/output contract, confirm units, and demonstrate a stock-shortage case with an unmet-data warning.

## Handoffs and done evidence

Share available-to-promise by SKU with Rajesh and Ranjit; supplier incoming stock with Rohit; report source/state version through Ruthwar’s contract. Done when shortage/reorder outputs are reproducible and no negative availability is silently accepted.

## Shared obligations

Add one normal and one discrepancy/missing-data case, sample input/output, documentation, peer review and demo explanation. No model-generated stock arithmetic.
