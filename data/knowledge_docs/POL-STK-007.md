---
document_id: POL-STK-007
title: Physical-Stock Reconciliation Policy
doc_type: policy
version: "1.0"
status: approved
effective_from: 2026-11-15
supersedes: none
owner: Warehouse Operations
classification: synthetic
parties: all
skus: all
licence: CC0-1.0 (synthetic text authored for this BharatBiz capstone)
source_url: none
retrieved_on: none
---

# Physical-Stock Reconciliation Policy

SIMULATION ONLY. Synthetic policy for an academic capstone. Stock quantities and adjustments are fictional.

## 1. Purpose

This policy defines how a physical count is compared with system stock and how discrepancies are controlled before planning uses the result.

## 2. Definitions

- **Book stock**: on-hand stock recorded in the versioned business state.
- **Counted stock**: quantity physically counted for a SKU and location.
- **Reserved stock**: stock committed to another order and not available for reallocation.
- **Usable stock**: available stock after reservations, holds and approved adjustments.
- **Variance**: counted stock minus book stock.

## 3. Rules

**R1 - Identify the count.** Every count records SKU, location, unit, counter, timestamp and count sheet id.

**R2 - Count in the catalogue unit.** Cases, pieces, kilograms and litres must not be silently converted. A conversion requires an approved pack rule.

**R3 - Separate physical and reserved stock.** A count does not release stock reserved for another order. Reservations are checked before usable stock is calculated.

**R4 - Investigate material variances.** A variance above the configured tolerance is held for recount and supervisor review. The tolerance is a state parameter, not an improvised judgement.

**R5 - No silent correction.** A book-stock adjustment records old quantity, new quantity, reason, evidence, approver and state version.

**R6 - Planning uses approved stock only.** Unapproved counts and disputed variances are excluded from fulfilment planning.

**R7 - No physical action from approval.** Approving a simulated adjustment changes a demo record only; it does not move, receive or dispose of goods.

## 4. Audit

The system retains the original book quantity, count, variance, recount result and approval. A later count creates a new record rather than rewriting history.

## 5. Example

Book stock is 56 litres and the count is 52. The variance is -4 litres. The operator checks open reservations, performs a recount if the tolerance requires it, and uses 52 only after the adjustment is approved.
