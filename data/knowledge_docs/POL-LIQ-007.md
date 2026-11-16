---
document_id: POL-LIQ-007
title: Liquidity and Cash-Flow Control Policy
doc_type: policy
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

# Liquidity and Cash-Flow Control Policy

SIMULATION ONLY. Synthetic policy for an academic capstone. It is not financial advice or a real credit decision.

## 1. Purpose

This policy controls whether a simulated fulfilment or procurement plan can be funded while preserving the approved operating cash buffer. It complements POL-CSH-002.

## 2. Definitions

- **Opening cash**: cash in the approved state at the as-of date.
- **Committed outflow**: the immediate procurement cost of the candidate plan.
- **Projected ending cash**: opening cash less committed outflow and other approved outflows in scope.
- **Liquidity headroom**: projected ending cash less the minimum cash buffer.

## 3. Rules

**R1 - Use a versioned cash position.** Cash is read from the approved state and tied to its state version.

**R2 - Count the full immediate outflow.** Expected retailer receipts, uncertain collections and unapproved credit are not netted against procurement cost.

**R3 - Exclude breaches.** A plan with negative liquidity headroom is removed before ranking and cannot be approved as a costly alternative.

**R4 - Show the calculation.** Review cards display opening cash, outflow, ending cash, minimum buffer and headroom.

**R5 - Escalate changes.** A cash change, price change, payment-term change or new commitment invalidates the prior liquidity check.

**R6 - No payment execution.** Approval does not transfer funds, create credit or notify a supplier.

## 4. Example

Opening cash of ₹2,50,000, a minimum buffer of ₹50,000 and an immediate outflow of ₹4,876.46 produce ending cash of ₹2,45,123.54 and headroom of ₹1,95,123.54. The plan passes this check.

## 5. Audit

The ledger stores the state version and every input used in the liquidity calculation. A later recalculation creates a new result and does not edit the prior review.
