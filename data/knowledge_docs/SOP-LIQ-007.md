---
document_id: SOP-LIQ-007
title: Liquidity Monitoring and Approval SOP
doc_type: sop
version: "1.0"
status: approved
effective_from: 2026-11-15
supersedes: none
owner: Finance Operations
classification: synthetic
parties: SUP-002, SUP-003, SUP-005
skus: all
licence: CC0-1.0 (synthetic text authored for this BharatBiz capstone)
source_url: none
retrieved_on: none
---

# Liquidity Monitoring and Approval SOP

SIMULATION ONLY. Synthetic operating procedure for an academic capstone.

## 1. Trigger

Run this procedure before a procurement plan enters review and whenever price, quantity, cash, payment terms or the state version changes.

## 2. Procedure

1. Confirm the state version and as-of date.
2. Read opening cash and the minimum cash buffer.
3. List the candidate plan's full immediate outflow and any other approved in-scope outflows.
4. Calculate projected ending cash and liquidity headroom deterministically.
5. Mark the candidate affordable only when headroom is zero or positive.
6. Exclude unaffordable candidates before plan ranking and record the exclusion reason.
7. Display the five liquidity values on the review card.
8. If any input is stale or missing, route the item to finance triage rather than estimating it.

## 3. Review checklist

The reviewer confirms that expected sales were not netted, supplier terms were not treated as credit unless the state explicitly models them, and the selected plan remains affordable in the recorded state version.

## 4. Completion

Store the calculation with the plan id and state version. Approval closes a recommendation only; it never executes a payment.
