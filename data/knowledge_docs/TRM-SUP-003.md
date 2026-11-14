---
document_id: TRM-SUP-003
title: Supplier Terms - Krishna Rice Mills (SUP-003)
doc_type: supplier_terms
version: "1.9"
status: approved
effective_from: 2026-05-01
supersedes: TRM-SUP-003 v1.8 (2025-11-15)
owner: Procurement
classification: synthetic
parties: SUP-003
skus: SKU-001, SKU-002, SKU-003, SKU-005, SKU-006, SKU-007, SKU-009, SKU-010, SKU-012
licence: CC0-1.0 (synthetic text authored for this BharatBiz capstone)
source_url: none
retrieved_on: none
---

# Supplier Terms - Krishna Rice Mills

SIMULATION ONLY. Synthetic supplier terms for an academic capstone. Krishna Rice Mills is a fictional party.

## 1. Commercial summary

| Item | Term |
| --- | --- |
| Supplier id | SUP-003 |
| Lead time | 3 days from confirmed order |
| Payment terms | 14 days from delivery |
| Quote validity | 7 days from issue |
| Delay notice | 24 hours before dispatch |
| Short-delivery credit note | 14 days from reconciliation |

## 2. Ordering

**2.1 Minimum order quantity.** Per line: 1 unit for Rice 5 kg bag; 5 units for Rice 10 kg bag, Cooking oil 1 L pouch, Biscuits family carton, Biscuits small carton, Soap case, Tea 1 kg pack and Toothpaste case; 10 units for Beverage crate.

**2.2 Capacity.** Committed capacity per SKU per cycle is stated in the supplier offer. Exceeding it requires written confirmation; the planner must not assume extra capacity.

**2.3 Batch and lot.** Each delivery carries a batch or lot code. The code is recorded against the delivery and quoted in any quality dispute.

## 3. Delivery and delay

**3.1 Lead time.** Three days from confirmed order. The planner's arrival date is derived from this lead time, not from an optimistic reading of the message.

**3.2 Delay notice.** At least 24 hours before dispatch. The notice must give either a revised date or an explicit "date not confirmed".

**3.3 Substitution during a delay.** This supplier may propose an alternative pack or grade. A proposal is not acceptance: it requires written acceptance from the distributor and the retailer before it is planned. See POL-SUB-003.

**3.4 Partial dispatch.** The supplier may split a line only with 24 hours' notice. A split is handled under SOP-SHT-003, never averaged into a single arrival date.

## 4. Price

**4.1 Quote validity.** Seven days. After expiry the rate must be re-confirmed in writing.

**4.2 Revision on open orders.** For an order already confirmed, a price revision requires 3 days' written notice and does not apply to units already dispatched.

**4.3 Taxes.** Rates exclude GST. Classification and rate are per REG-GST-2025-09; rice that is pre-packaged and labelled is treated differently from loose rice for GST purposes.

## 5. Quality and labelling

**5.1 Food safety.** Goods must comply with FSSAI requirements, including the licence number and the declarations required on a pre-packaged food label. See REG-FSSAI-LAB-2020.

**5.2 Pack declarations.** Net quantity, retail sale price and consumer-care details must be declared as required by the Legal Metrology (Packaged Commodities) Rules. See REG-LMPC-2011-R6.

**5.3 Rejection.** Non-compliant or short goods may be rejected at the supplier's cost. Rejection does not cancel the retailer order; it triggers re-planning.

## 6. Credit and payment

Payment is due 14 days from delivery. The payment term does not create credit in the distributor's cash projection: the planning system treats procurement cost as an immediate outflow under POL-CSH-002.
