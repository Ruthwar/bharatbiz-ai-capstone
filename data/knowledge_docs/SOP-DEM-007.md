---
document_id: SOP-DEM-007
title: Demand Simulation SOP
doc_type: sop
version: "1.0"
status: approved
effective_from: 2026-11-15
supersedes: none
owner: Demand Planning
classification: synthetic
parties: RET-all, SUP-002, SUP-003, SUP-005
skus: all
licence: CC0-1.0 (synthetic text authored for this BharatBiz capstone)
source_url: none
retrieved_on: none
---

# Demand Simulation SOP

SIMULATION ONLY. Synthetic operating procedure for an academic capstone.

## 1. Trigger

Run this procedure when a reviewer asks what happens if demand rises, falls, shifts by date or changes for a named SKU. Do not use it to replace a confirmed order.

## 2. Procedure

1. Record the scenario id, requester, state version and planning horizon.
2. Load the baseline orders, usable stock, supplier offers, prices, lead times and cash buffer.
3. Write the assumption in plain language and as structured inputs: SKU, dates, units or factor.
4. Validate that the SKU and dates exist and that the adjusted demand is non-negative.
5. Run the deterministic planner using the ordinary affordability and ranking rules.
6. Compare baseline and scenario results for unmet units, late units, arrival date, cost, ending cash and headroom.
7. Save the inputs, outputs and any validation error. Route material adverse changes to human review.

## 3. Controls

- Never edit the source order to create a scenario.
- Never combine scenarios unless each assumption is separately recorded.
- Do not use scenario output as evidence that a retailer requested more stock.
- A failed or incomplete run is labelled failed; it is not silently filled in.

## 4. Review checklist

The reviewer confirms the state version, horizon, assumption, candidate set, ranking result and cash check. If any input is stale, the run is repeated against the current approved state.

## 5. Example

For a +10% demand case, the operator copies the baseline into a new scenario, increases only the selected demand lines, reruns planning and reports the difference. The baseline remains unchanged.
