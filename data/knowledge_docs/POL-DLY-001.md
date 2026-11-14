---
document_id: POL-DLY-001
title: Supplier Delay Handling Policy
doc_type: policy
version: "3.1"
status: approved
effective_from: 2026-04-01
supersedes: POL-DLY-001 v3.0 (2025-10-01)
owner: Category Operations
classification: synthetic
parties: SUP-002, SUP-003, SUP-005
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

**R4 - Rank in a fixed order.** Candidates are compared lexicographically on: fewest unmet units, then fewest late units, then earliest scenario arrival date, then lowest total cost, then candidate id. The order is not a weighted score and must not be adjusted case by case. This means an earlier arrival wins over a cheaper plan when coverage and lateness are equal.

**R5 - Remove unaffordable plans before ranking.** A plan whose projected ending cash falls below the minimum cash buffer is not a candidate. It is excluded, not ranked as expensive. Cash rules are held in POL-CSH-002.

**R6 - Identify the cheapest acceptable trade-off for the reviewer.** When the selected plan costs more than an alternative with the same unmet units, the review card must state the extra rupees and what they buy: late units avoided, or days earlier. The reviewer sees the comparison, not just the winner.

**R7 - Re-plan when facts change.** A supplier cancellation, a confirmed revised date, a quantity change or a price change invalidates the current plan. Re-planning uses the same rules; approval behaviour is governed by POL-PRC-005.

**R8 - Substitution is not implicit.** Buying a different pack size or a different SKU is not a delay remedy under this policy. It requires the substitution rules in POL-SUB-003 and the retailer's consent.

**R9 - Escalate rather than guess.** Missing slots, conflicting facts, unregistered intents, failed validation and exhausted follow-up rounds all route to human triage with the transcript and the reason. Nothing is dropped.

## 4. Worked example

A supplier reports a two-day delay for Cooking oil 1 L pouch. The planning horizon is 2026-11-04. Open orders request 102 litres; usable stock is 56 litres, leaving 46 litres to buy. The stock-only plan leaves 46 units unmet. Every supplier plan that covers 46 units arrives after at least one requested delivery date, so the plans tie on unmet units and on 28 late units. The tie is broken by earliest scenario arrival, then by cost. The review card names the extra cost of the selected plan against the next-best alternative and the late units it avoids.

## 5. Audit

Every decision records the plan id, the state version, the selected supplier, the ranking inputs and the evidence span from the supplier message. A plan approved in one state version cannot be reused in another.
