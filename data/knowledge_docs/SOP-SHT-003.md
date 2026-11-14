---
document_id: SOP-SHT-003
title: Partial Dispatch and Short Delivery SOP
doc_type: sop
version: "2.0"
status: approved
effective_from: 2026-10-01
supersedes: SOP-SHT-003 v1.5 (2026-04-01)
owner: Warehouse Operations
classification: synthetic
parties: SUP-002, SUP-003, SUP-005
skus: SKU-003, SKU-004, SKU-005, SKU-006, SKU-009
licence: CC0-1.0 (synthetic text authored for this BharatBiz capstone)
source_url: none
retrieved_on: none
---

# Partial Dispatch and Short Delivery SOP

SIMULATION ONLY. Synthetic operating procedure for an academic capstone.

## 1. Trigger

Any of the following is a partial dispatch case:

- The supplier writes "60% now, 40% next week", "half today", or gives two quantities and two dates for one order.
- The delivery arrives with fewer units than the purchase order line.
- The supplier confirms the original date for some units and a later date for the rest.

## 2. Why it is escalated, not averaged

The planner treats all incoming units for the affected SKU as delayed. It has one arrival date per supplier option. A split delivery therefore cannot be represented without inventing an arrival date for one of the parts. Averaging the dates produces a number no supplier agreed to, and the review card would present it as fact.

## 3. Procedure

1. Acknowledge receipt with the standard template. Do not confirm the split.
2. Record the message, sender and any quantities stated, with evidence spans.
3. Route to human triage with reason "partial_dispatch_not_modelled".
4. The human creates two line-level records for the order: units arriving on the first date, units arriving on the second.
5. Re-run planning per line if both lines affect orders inside the horizon. Do not merge the two results into one plan.
6. If the supplier's split leaves the second quantity unconfirmed, record the second quantity as unknown and plan only the confirmed part.

## 4. Short delivery on arrival

1. Reconcile the received quantity against the purchase order line before signing.
2. Record the shortfall and notify the supplier within 24 hours.
3. Apply the supplier's short-delivery clause: credit note within 7 days for SUP-002 and SUP-005, 14 days for SUP-003.
4. Re-plan any retailer order that can no longer be met. Use the normal ranking rules; do not give the short supplier priority as compensation.

## 5. Prohibited shortcuts

- Splitting a delayed quantity into two equal halves to "make it fit" the planner.
- Marking a partial delivery complete in the ledger.
- Promising the retailer the second part's date before the supplier confirms it.
- Editing an approved plan to reflect the shortfall.

## 6. Example

A supplier writes: "12 units of Cooking oil 1 L pouch delayed by two days; 8 of them can go tomorrow." The planner cannot hold two dates for one line. The item is triaged, the human records 8 units for tomorrow and 4 units unconfirmed, and each line is planned separately. The retailer is told nothing until a human approves a message.
