---
document_id: POL-CSH-002
title: Cash Buffer and Affordability Policy
doc_type: policy
version: "2.4"
status: approved
effective_from: 2026-06-01
supersedes: POL-CSH-002 v2.3 (2026-01-15)
owner: Finance Operations
classification: synthetic
parties: SUP-002, SUP-003, SUP-005
skus: SKU-001, SKU-002, SKU-003, SKU-004, SKU-005, SKU-006, SKU-007, SKU-008, SKU-009, SKU-010, SKU-011, SKU-012
licence: CC0-1.0 (synthetic text authored for this BharatBiz capstone)
source_url: none
retrieved_on: none
---

# Cash Buffer and Affordability Policy

SIMULATION ONLY. Synthetic policy for an academic capstone. Figures are fictional and must not be used for real credit or purchasing decisions.

## 1. Purpose

A fulfilment plan is only useful if the business can pay for it without breaching its operating buffer. This policy defines how procurement cost is checked against cash before a plan can be reviewed.

## 2. Definitions

- **Opening cash**: the cash balance recorded in the business state at the state's as-of date. For the 2026-11-05 synthetic state this is ₹2,50,000.
- **Minimum cash buffer**: the floor that ending cash must not cross. For the same state this is ₹50,000. The buffer is a state parameter, not a constant in code.
- **Headroom**: projected ending cash minus the minimum buffer. Headroom of zero is acceptable; negative headroom is not.
- **Immediate outflow**: the full procurement cost of a candidate plan is treated as leaving cash at once. There is no supplier credit in the projection even where payment terms exist.

## 3. Rules

**R1 - Exclude, do not penalise.** A candidate whose headroom is negative is removed from the candidate set before ranking. It must not appear as a very expensive option that loses on cost, because the ranking rule in POL-DLY-001 would then be acting on a plan the business cannot execute.

**R2 - Stock-only is always affordable if there is stock.** The stock-only plan carries no procurement outflow and remains a candidate. If it leaves units unmet, the reviewer sees the shortage explicitly.

**R3 - Do not net off expected sales.** Projected retailer receipts are not counted. Cash headroom is deliberately conservative; a plan that needs tomorrow's collections to clear the buffer is not affordable today.

**R4 - Supplier payment terms do not create credit.** Payment terms of 7, 14 or 0 days are recorded for context, but the cash projection treats cost as an immediate outflow. A future revision may model the payment date; until then, terms must not be used to justify headroom.

**R5 - Show the headroom.** Every alternative in the review card displays the ending cash and the headroom, so a reviewer can see how close the selected plan runs to the floor.

**R6 - No payment is executed.** Approval changes a demo record only. No money moves, no purchase order is issued and no supplier is notified. See POL-COM-006.

## 4. Worked example

If opening cash is ₹2,50,000 and a candidate plan costs ₹4,876.46, projected ending cash is ₹2,45,123.54 and headroom is ₹1,95,123.54, which clears the ₹50,000 buffer. The plan is a candidate. A plan costing ₹2,00,000 or more would project headroom at or below zero and would be excluded before ranking, even if it covered every unit exactly.

## 5. Known limitation

A mid-delay price change is read from state at calculation time. There is no automatic invalidation of an approval already granted when the underlying price later moves; see POL-PRC-005. The cash check is only as current as the cited state version.
