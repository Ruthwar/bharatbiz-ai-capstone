---
document_id: POL-DEM-007
title: Demand Simulation and Scenario Policy
doc_type: policy
version: "1.0"
status: approved
effective_from: 2026-11-15
supersedes: none
owner: Demand Planning
classification: synthetic
parties: all
skus: all
licence: CC0-1.0 (synthetic text authored for this BharatBiz capstone)
source_url: none
retrieved_on: none
---

# Demand Simulation and Scenario Policy

SIMULATION ONLY. Synthetic policy for an academic capstone. A scenario is not a forecast or a commercial commitment.

## 1. Purpose and scope

This policy governs the creation, comparison and use of demand scenarios for inventory and fulfilment decisions. It applies to simulated retailer demand, replenishment requirements and what-if cases. It does not authorise a purchase, allocation, price change or retailer communication.

## 2. Definitions

- **Baseline demand**: the demand recorded in the versioned business state for the selected horizon.
- **Scenario demand**: baseline demand modified by an explicitly stated simulation assumption.
- **Horizon**: the inclusive date range used by the simulation.
- **Sensitivity**: the change in unmet units, late units, cost or cash headroom caused by one changed input.

## 3. Rules

**R1 - Baseline first.** Every scenario starts from a named state version and records the baseline before any adjustment.

**R2 - Assumptions are visible.** A scenario must state the changed SKU, quantity, date range, factor and reason. Hidden adjustments are prohibited.

**R3 - No invented observations.** A simulation may use a labelled assumption or a cited historical input, but it must not present a model-generated number as an observed order.

**R4 - Deterministic inputs win.** Stock, prices, lead times, tax and supplier capacity come from the versioned business state. A scenario may alter demand only when the scenario explicitly permits it.

**R5 - Compare like with like.** Each run uses one mode selected by the reviewer, the named planning horizon, the eligible candidate set, verified outcomes and the same state version. When evaluating the modes across separate runs, keep those inputs constant. Deterministic mode follows its published ranking rule; Policy-grounded LLM mode uses applicable retrieved natural-language policies and records its rationale and policy versions.

**R6 - Simulation does not execute.** Running or approving a scenario changes a demo record only. It does not create an order, reserve stock, move money or message a party.

**R7 - Material changes require review.** A scenario that changes the selected plan, creates a cash-buffer breach or increases unmet or late units is shown to a human reviewer.

## 4. Required output

Each run records the scenario id, state version, baseline, assumptions, eligible and excluded plans, deterministic baseline result, policy-grounded model result or abstention, retrieved policy versions and citations, unmet and late units, total cost, ending cash, headroom and run timestamp. Results that cannot be reproduced from these fields are invalid.

## 5. Example

The baseline requests 100 units of a SKU inside the horizon. A +20% demand scenario records a request of 120 units, creates and verifies the candidate plans, then shows the deterministic baseline beside the policy-grounded model recommendation using the same options. It shows any difference in unmet units and cash impact. The scenario must not alter the baseline order to 120 units.

## 6. Audit

Scenario inputs and outputs remain linked to the state version used. Re-running after a state change creates a new scenario result; it does not overwrite the earlier result.
