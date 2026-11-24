---
document_id: SOP-STV-004
title: State Version and Refresh SOP
doc_type: sop
version: "1.8"
status: approved
effective_from: 2026-10-05
supersedes: SOP-STV-004 v1.7 (2026-06-20)
owner: Data Operations
classification: synthetic
parties: all
skus: all
licence: CC0-1.0 (synthetic text authored for this BharatBiz capstone)
source_url: none
retrieved_on: none
---

# State Version and Refresh SOP

SIMULATION ONLY. Synthetic operating procedure for an academic capstone.

## 1. Principle

Every message is interpreted against one version of the business state. The version that was used is recorded with the decision. A message is never silently re-interpreted against a newer state.

## 2. Where the version appears

- Every inbound submission carries a `state_version` string.
- The loaded business state carries its own `state_version`.
- The two must match exactly. The current demo state is `synthetic-v3-live-20261123`.
- The review record stores the state version shown to the approver.

## 3. Mismatch handling

1. The message still receives a receipt acknowledgement. The sender is not told that the message was rejected.
2. The item is routed to human triage with `processing_error` describing the mismatch.
3. The extracted facts are kept for the record but no plan is produced.
4. Nothing is re-run automatically against the current state. A human decides whether to resubmit against the correct version.

## 4. Refreshing the demo

1. Stop the API process.
2. Run `scripts/reset_demo.py` to clear results, intakes and the review queue.
3. Replace or regenerate the synthetic state, then update `state_version` in `business_state.json` and in the scenario fixture together.
4. Restart the API and confirm the review queue is empty before the demo.

Resetting the ledger does not change the state files. Changing the state files without changing the version string is prohibited: it produces decisions whose recorded version cannot be reproduced.

## 5. Why the version matters for review

An approval is a decision about a specific set of orders, stock, prices and dates. If those change, the approval must be re-taken. The version string is how the system proves which set was seen. Without it, an approver cannot answer "what did I actually approve?".

## 6. Interaction with price changes

A price message under a new state version does not retroactively invalidate an approval on its own. POL-PRC-005 defines the invalidation rule; this SOP only guarantees that the version was recorded so the rule can be applied.
