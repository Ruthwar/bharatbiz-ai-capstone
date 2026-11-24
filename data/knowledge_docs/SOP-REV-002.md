---
document_id: SOP-REV-002
title: Human Review Queue SOP
doc_type: sop
version: "3.3"
status: approved
effective_from: 2026-10-15
supersedes: SOP-REV-002 v3.2 (2026-09-15)
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

An operational item reaches review after candidate plans have been generated and checked. The UI provides one **Recommendation mode** control: Deterministic or Policy-grounded LLM. A run uses only the selected mode. Triage items and recommendation items share a queue but are labelled differently.

## 2. Reading a recommendation

1. **Attempted coverage.** Usable stock, requested units, units bought, and the resulting unmet and late units.
2. **The selected mode and recommendation.** Deterministic mode shows the fixed-ranking result and ranking inputs. Policy-grounded LLM mode shows the model's eligible candidate or an explicit abstention, with natural-language policy rationale and citations. Do not imply that policies drove a deterministic result.
3. **The alternatives.** Every eligible candidate with cost, arrival estimate, late units, unmet units, ending cash and headroom. Excluded candidates remain visible with their reasons but are clearly not selectable.
4. **The trade-off.** Show the cost difference and verified service difference between the selected recommendation and alternatives.
5. **Verification.** The selected recommendation must point to a candidate that passed independent checks. A failed verification is not approvable; it is a defect report.
6. **Evidence.** Each extracted fact with its exact span and offsets. A fact that is not in the message is a validation failure, not a judgement call.
7. **Assumptions and unknowns.** An unconfirmed revised date appears as an unknown. It is never filled in by the reviewer to make the card look complete.
8. **Policy references.** In LLM mode, show retrieved policy and term sections with document id and effective date. The reviewer checks applicability, version and how the natural-language priority informed the model result.

## 3. Decisions

**Approve** only when: the selected mode returned an eligible, independently verified candidate, evidence matches, and the mode-specific rationale is adequate. Record the candidate, selected mode, approver, reason and state version. A model abstention is not a candidate; the reviewer may explicitly switch to Deterministic and start a new run, or route the item for triage. Never silently fall back.

**Reject** with a reason. Rejection does not delete the item; it stays in history.

**Re-open** when a fact has changed. Do not edit an approved item's numbers. A change produces a new item under POL-PRC-005.

## 4. Queue discipline

- Oldest item first, unless an item's state version is stale, in which case it is reviewed against the version it was created with and flagged.
- One reviewer decision per item. Two conflicting decisions is a data error, not a tie-break.
- An item may be approved at most once. Repeated approval is idempotent in the ledger and must not create a second record.

## 5. What approval does not do

Approval does not place an order, pay a supplier, change stock, message a retailer or promise a date. It closes the review of a recommendation. See POL-COM-006.

## 6. Common review errors

- Assuming both modes ran when only one was selected, or treating deterministic ranking as policy interpretation.
- Approving a model recommendation whose cited rules were not retrieved or do not support the stated trade-off.
- Selecting an excluded candidate because its outcome looks attractive.
- Treating the stock-only plan as free: it is affordable but may leave units unmet.
- Approving against a stale state version after a price or order change.
- Ignoring the headroom column because all candidates look affordable.
