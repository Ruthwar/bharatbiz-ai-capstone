---
document_id: POL-PRC-005
title: Price Validity and Re-approval Policy
doc_type: policy
version: "1.3"
status: approved
effective_from: 2026-08-01
supersedes: POL-PRC-005 v1.2 (2026-02-10)
owner: Commercial
classification: synthetic
parties: SUP-002, SUP-003, SUP-005
skus: SKU-003, SKU-004, SKU-005, SKU-006
licence: CC0-1.0 (synthetic text authored for this BharatBiz capstone)
source_url: none
retrieved_on: none
---

# Price Validity and Re-approval Policy

SIMULATION ONLY. Synthetic policy for an academic capstone.

## 1. Purpose

An approval is a decision about a specific deal at a specific price. This policy defines when that approval stops being valid.

## 2. Rules

**R1 - Approval is bound to inputs.** An approval covers the plan id, the state version, the supplier, the SKU, the quantity, the unit rate, the total cost and the scenario arrival date shown to the approver. If any of these changes, the approval is void and the item returns to review.

**R2 - No automatic re-pricing.** The system never substitutes a new rate into an approved plan and marks it approved again. A changed rate produces a new plan and a new review item, with the old decision kept in history.

**R3 - Prices are read at calculation time.** Unit cost comes from the versioned business state or the supplier offer attached to that state. There is no separate price cache that can drift.

**R4 - Quote validity comes from the supplier terms.** A supplier quote is treated as valid for the number of days stated in that supplier's terms: 7 days for SUP-002, SUP-003 and SUP-005. Validity is shown on the review card; an expired quote must be re-confirmed before approval.

**R5 - Price up, quantity up, date worse.** Any change that increases total cost, increases the quantity needed, or pushes the arrival date later voids the approval. A change that strictly improves all three may be re-planned but still requires a fresh approval.

**R6 - Tax changes are price changes.** If the applicable GST rate for the SKU changes, the landed cost changes. Catalogued rates are dated; a rate change after the approval voids it.

## 3. Known gap

A price message that arrives **during** a delay is not a first-class intent in this slice. The supplier-delay handler does not parse "and the rate is now ₹X". The message is acknowledged, the new rate is not applied, and the item is routed to human triage. This is the highest-value gap to close next, because it is the case where an approved plan can silently become wrong.

## 4. Worked example

A reviewer approves 46 litres at ₹106.01 with arrival 2026-11-04. Two days later the supplier re-quotes ₹109.50. The approved plan is not edited. A new candidate set is produced at the new rate, the old approval is marked void, and a new review item is created with the difference shown. Nothing is bought and no supplier is messaged.
