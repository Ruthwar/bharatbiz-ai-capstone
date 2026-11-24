---
document_id: POL-DLY-001
title: Supplier Delay Handling Policy
doc_type: policy
version: "3.2"
status: approved
effective_from: 2026-10-15
supersedes: POL-DLY-001 v3.1 (2026-04-01)
owner: Category Operations
classification: synthetic
parties: all
skus: SKU-003, SKU-004
licence: CC0-1.0 (synthetic text authored for this BharatBiz capstone)
source_url: none
retrieved_on: none
---

# Supplier Delay Handling Policy

SIMULATION ONLY. This is a synthetic document written for an academic capstone. It is not a real distributor policy. All parties, orders and amounts are fictional.

## 1. Purpose and scope

This policy governs how an unconfirmed or confirmed supplier delay on an open purchase order is turned into a reviewed fulfilment plan. It applies to every SKU where a supplier has reported that incoming units will arrive after the requested delivery date. It does not authorise anyone to place an order, pay a supplier or message a retailer.

## 2. Definitions

- **Delayed incoming units**: units already committed by the supplier but now expected after the order's requested delivery date.
- **Usable stock**: on-hand units minus reserved units. Reserved units belong to other orders and are never reallocated by this process.
- **Late units**: units delivered after the retailer's requested delivery date, even if they are eventually delivered.
- **Unmet units**: requested units that no plan covers at all.
- **Scenario arrival date**: the date a candidate supplier is expected to deliver, derived from that supplier's lead time, not from a promise in the message.

## 3. Rules

**R1 - Never promise a date.** A delayed supplier's message that says the revised date is "not confirmed" is recorded as an unknown. No plan, acknowledgement or review card may assert an arrival date that the supplier has not confirmed in writing.

**R2 - Verify before planning.** The affected SKU, the delayed units and the open orders due inside the planning horizon are read from the versioned business state, never from the message alone. If the SKU cannot be resolved against the product catalogue, the item goes to human triage.

**R3 - Candidate plans come from feasible offers only.** A supplier offer is a candidate only if the line meets its minimum order quantity, stays inside its capacity, and the lead time is known. The stock-only plan is always a candidate.

**R4 - Use the mode selected by the reviewer.** After applying the mandatory eligibility checks in this policy, POL-CSH-002 and POL-LIQ-007, run only the recommendation mode explicitly selected in the UI. The deterministic mode uses the fixed order of fewest unmet units, fewest late units, earliest scenario arrival, lowest total cost, then candidate id. The policy-grounded LLM mode follows POL-DEC-008 using the applicable natural-language policies. Do not blend the modes or silently switch modes.

**R5 - Remove unaffordable plans before either recommendation.** A plan whose projected ending cash falls below the minimum cash buffer is not eligible. Exclude it before deterministic ranking and before the model receives its options; do not show it as a viable option. Cash rules are held in POL-CSH-002 and POL-LIQ-007.

**R6 - Identify the cost and service trade-off for the reviewer.** When the chosen plan costs more than another eligible plan, the review card states the extra rupees and the verified service difference: late or unmet units changed, or estimated arrival difference. Show the selected mode and its rationale clearly.

**R7 - Re-plan when facts change.** A supplier cancellation, a confirmed revised date, a quantity change or a price change invalidates the current plan. Re-planning uses the same rules; approval behaviour is governed by POL-PRC-005.

**R8 - Substitution is not implicit.** Buying a different pack size or a different SKU is not a delay remedy under this policy. It requires the substitution rules in POL-SUB-003 and the retailer's consent.

**R9 - Escalate rather than guess.** Missing slots, conflicting facts, unregistered intents, failed validation and exhausted follow-up rounds all route to human triage with the transcript and the reason. Nothing is dropped.

**R10 - Honor the selected mode.** Show the selected mode, its chosen candidate, verified outcomes, exclusions and rationale. In deterministic mode, explain the fixed ranking result. In policy-grounded LLM mode, explain service and cost trade-offs with retrieved citations. If the LLM mode is unavailable or policy support is missing or insufficient, show an explicit unavailable or abstained result and route the case to a human; never silently substitute the deterministic result.

## 4. Worked example

A supplier reports a two-day delay for Cooking oil 1 L pouch. The planning horizon is 2026-11-04. Open orders request 102 litres; usable stock is 56 litres, leaving 46 litres to buy. The stock-only plan leaves 46 units unmet. The reviewer selects **Deterministic** or **Policy-grounded LLM** in the UI. Deterministic mode applies the fixed ranking. LLM mode receives the same eligible plans and retrieved service, cost and delay policies; it may recommend a lower-cost plan when service is materially similar or an earlier plan when documented deadlines support the benefit. The review card shows the selected mode, recommendation and supporting information. The reviewer then approves or rejects that recommendation.

## 5. Audit

Every run records the event and state versions, the selected mode, eligible candidate ids, and the evidence span from the supplier message. Deterministic runs record ranking inputs and result. LLM runs record retrieved policy versions, model and prompt versions, citations, and result or abstention. The human records the approval decision and reason. A plan approved in one state version cannot be reused in another.
