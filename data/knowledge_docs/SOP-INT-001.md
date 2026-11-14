---
document_id: SOP-INT-001
title: Inbound Message Intake and Question SOP
doc_type: sop
version: "4.0"
status: approved
effective_from: 2026-09-01
supersedes: SOP-INT-001 v3.4 (2026-03-01)
owner: Operations Desk
classification: synthetic
parties: SUP-002, SUP-003, SUP-005, RET-all
skus: SKU-003, SKU-004
licence: CC0-1.0 (synthetic text authored for this BharatBiz capstone)
source_url: none
retrieved_on: none
---

# Inbound Message Intake and Question SOP

SIMULATION ONLY. Synthetic operating procedure for an academic capstone.

## 1. Step 1 - Verify the sender before reading the content

1. Check that the message carries an authenticated sender, not a self-declared one.
2. For a supplier delay, the sender must be a **supplier** account.
3. The supplier id the message reports must match the sending account. A message from SUP-002 that reports a delay for SUP-005 is rejected for processing.
4. A retailer cannot report a supplier's dispatch delay. They can report that a delivery has not arrived; that is a different intent.

A failed identity check still produces a receipt acknowledgement. The item goes to human triage with the reason "authorization_failed".

## 2. Step 2 - Detect intent

Intents in the current vocabulary include supplier delay, delivery complaint, product request and scheme question. Only supplier delay has a planning handler. An unregistered intent is acknowledged and triaged; it is not forced into the nearest known intent.

A single message may contain two intents. The primary intent is processed; the second is forked into its own item and never absorbed silently.

## 3. Step 3 - Fill required slots

For a supplier delay, the decision needs:

| Slot | Required | Notes |
| --- | --- | --- |
| supplier_id | yes | Must equal the verified sender |
| sku_id | yes | Must resolve in the product catalogue |
| delay_days | yes | Positive whole days; "a few days" is not a value |
| revised_date | no | Recorded when stated; never inferred |
| purchase_order_reference | no | Recorded; not needed for planning |

Rules for questions:

1. **One question per turn.** The system asks about the missing slot with the largest effect on the plan, usually the product first, then the delay.
2. **Maximum two questions.** After two rounds the item goes to triage with the transcript. There is no third question.
3. **Decision-relevant only.** If a missing field cannot change the plan, it is not asked for.
4. **Right party only.** A retailer is never asked for a supplier's dispatch date; a supplier is never asked to confirm a retailer's shelf stock.
5. **Template wording.** Questions are fixed strings keyed to a slot, not generated prose. They ask for a fact and offer no advice or estimate.

## 4. Step 4 - Validate deterministically

The model, if used, proposes facts. A deterministic validator confirms that the span exists in the message, that offsets match the text, that the SKU is in the catalogue, and that the delay is a number. Failed validation routes to triage; it does not trigger a re-ask loop.

## 5. Step 5 - Route

A validated supplier delay with all required slots goes to planning. Everything else goes to human triage with: the raw message, the extracted facts, the missing slots, the rounds used and the reason.
