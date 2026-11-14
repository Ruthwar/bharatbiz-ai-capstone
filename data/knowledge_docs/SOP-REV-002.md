---
document_id: SOP-REV-002
title: Human Review Queue SOP
doc_type: sop
version: "3.2"
status: approved
effective_from: 2026-09-15
supersedes: SOP-REV-002 v3.1 (2026-05-01)
owner: Operations Desk
classification: synthetic
parties: SUP-002, SUP-003, SUP-005
skus: SKU-003, SKU-004, SKU-005, SKU-006
licence: CC0-1.0 (synthetic text authored for this BharatBiz capstone)
source_url: none
retrieved_on: none
---

# Human Review Queue SOP

SIMULATION ONLY. Synthetic operating procedure for an academic capstone. Approval here changes a demo record only.

## 1. What reaches the queue

An item reaches review when a plan has been selected and independently verified, or when a message has been triaged. Triage items and plan items share a queue but are labelled differently.

## 2. Reading a plan item - fixed order

1. **Attempted coverage.** Usable stock, requested units, units bought, and the resulting unmet and late units.
2. **The alternatives table.** Every candidate with cost, arrival date, late units, unmet units, ending cash and headroom. The selected row is marked.
3. **The trade-off line.** If the selected plan costs more than an alternative with the same coverage, the card states how many rupees buy how many fewer late units, or how many days earlier.
4. **Verification.** The independent check must show zero violations. A card with a failed verification is not approvable; it is a defect report.
5. **Evidence.** Each extracted fact with its exact span and offsets. A fact that is not in the message is a validation failure, not a judgement call.
6. **Assumptions and unknowns.** An unconfirmed revised date appears as an unknown. It is never filled in by the reviewer to make the card look complete.
7. **Policy references.** Retrieved policy and term sections with document id and effective date. The reviewer uses these to check that the rule applied is the current rule.

## 3. Decisions

**Approve** only when: verification passes, evidence matches, the selected plan is the one the ranking rule produces, and the policy references support the rule applied. Approval records the approver, the plan id and the state version.

**Reject** with a reason. Rejection does not delete the item; it stays in history.

**Re-open** when a fact has changed. Do not edit an approved item's numbers. A change produces a new item under POL-PRC-005.

## 4. Queue discipline

- Oldest item first, unless an item's state version is stale, in which case it is reviewed against the version it was created with and flagged.
- One reviewer decision per item. Two conflicting decisions is a data error, not a tie-break.
- An item may be approved at most once. Repeated approval is idempotent in the ledger and must not create a second record.

## 5. What approval does not do

Approval does not place an order, pay a supplier, change stock, message a retailer or promise a date. It closes the review of a recommendation. See POL-COM-006.

## 6. Common review errors

- Approving a plan because it is cheapest when the ranking rule selected it for earliest arrival.
- Treating the stock-only plan as free: it is affordable but may leave units unmet.
- Approving against a stale state version after a price or order change.
- Ignoring the headroom column because all candidates look affordable.
