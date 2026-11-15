---
document_id: SOP-STK-007
title: Physical-Stock Reconciliation SOP
doc_type: sop
version: "1.0"
status: approved
effective_from: 2026-11-15
supersedes: none
owner: Warehouse Operations
classification: synthetic
parties: RET-all, SUP-002, SUP-003, SUP-005
skus: all
licence: CC0-1.0 (synthetic text authored for this BharatBiz capstone)
source_url: none
retrieved_on: none
---

# Physical-Stock Reconciliation SOP

SIMULATION ONLY. Synthetic operating procedure for an academic capstone.

## 1. Trigger

Use this procedure for a scheduled count, a stockout that conflicts with book stock, a receiving discrepancy or a material variance.

## 2. Procedure

1. Freeze the relevant count location and identify the state version.
2. Print or open the count list with SKU, description and catalogue unit.
3. Count usable, damaged, held and reserved quantities separately.
4. Record the counter, timestamp and evidence for every line; do not leave blank quantities.
5. Calculate variance against book stock and compare it with the configured tolerance.
6. Recount any material or disputed line with a second counter.
7. Route unresolved differences to a supervisor with reason `stock_variance_unresolved`.
8. Apply an approved adjustment, preserve the before-and-after quantities and refresh the state version.
9. Re-run any affected plan against the new approved state.

## 3. Prohibited shortcuts

- Changing book stock to make an order appear fulfilable.
- Treating damaged or reserved goods as usable.
- Backdating a count or deleting an adverse variance.
- Reusing a plan created before an approved stock adjustment.

## 4. Completion check

The reconciliation is complete only when every line is approved, held with a reason or explicitly zero-counted, and the ledger shows the count sheet id.
