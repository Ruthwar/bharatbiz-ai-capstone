---
document_id: TRM-SUP-002
title: Supplier Terms - Balaji Wholesale Distributors (SUP-002)
doc_type: supplier_terms
version: "2.2"
status: approved
effective_from: 2026-04-15
supersedes: TRM-SUP-002 v2.1 (2025-09-01)
owner: Procurement
classification: synthetic
parties: SUP-002
skus: SKU-002, SKU-003, SKU-004, SKU-006, SKU-007, SKU-010, SKU-011, SKU-012
licence: CC0-1.0 (synthetic text authored for this BharatBiz capstone)
source_url: none
retrieved_on: none
---

# Supplier Terms - Balaji Wholesale Distributors

SIMULATION ONLY. Synthetic supplier terms for an academic capstone. Balaji Wholesale Distributors is a fictional party.

## 1. Commercial summary

| Item | Term |
| --- | --- |
| Supplier id | SUP-002 |
| Lead time | 2 days from confirmed order |
| Payment terms | 7 days from delivery |
| Quote validity | 7 days from issue |
| Delay notice | 12 hours before the dispatch window |
| Short-delivery credit note | 7 days from reconciliation |

## 2. Ordering

**2.1 Minimum order quantity.** Per line, per SKU: 10 units for Cooking oil 1 L pouch, Cooking oil 5 L tin, Beverage crate, Detergent case and Toothpaste case; 5 units for Soap case; 1 unit for Rice 10 kg bag and Biscuits small carton. An order below the line minimum is not accepted and must not be presented to this supplier as a candidate.

**2.2 Capacity.** The supplier's committed capacity per SKU per cycle is recorded in the supplier offer. A request above capacity is either reduced to capacity or rejected; it is never partially accepted without written confirmation.

**2.3 Order confirmation.** An order exists only when this supplier confirms it in writing. A message that says "we will try" is not a confirmation and does not create an arrival date.

## 3. Delivery and delay

**3.1 Lead time.** Two days from confirmed order, measured in working days. The planner derives the scenario arrival date from this lead time and the order date; it does not accept a date from the message as confirmed unless the supplier states it explicitly.

**3.2 Delay notice.** The supplier must notify a delay at least 12 hours before the dispatch window. A notice received after the window is recorded as late notice and separated from the delay itself.

**3.3 Revised date.** A delay notice must state a revised date or state that the date is not confirmed. "Not confirmed" is an acceptable notice and is recorded as an unknown. It is not treated as an estimate.

**3.4 Cancellation.** The supplier may cancel an unconfirmed line without penalty. A confirmed line may be cancelled only with the distributor's written agreement; the planner treats a cancellation as a new fact and re-plans.

## 4. Price

**4.1 Quote validity.** A quoted rate holds for 7 days. After that, the supplier may re-quote. A re-quote is a price change under POL-PRC-005 and voids any approval that used the old rate.

**4.2 No retrospective pricing.** A rate applies from the date it is issued. The supplier may not apply a new rate to an order confirmed before the issue date without agreement.

**4.3 Taxes.** Rates are exclusive of GST. The applicable GST rate depends on the SKU classification; see REG-GST-2025-09. The supplier raises the tax invoice at the rate in force on the invoice date.

## 5. Quality and labelling

**5.1 Specification.** Goods must match the agreed specification and pack description. A pack-size change is a substitution and requires prior written acceptance from the distributor and the retailer.

**5.2 Labelling.** Pre-packaged food supplied under these terms must carry the declarations required by FSSAI and the Legal Metrology (Packaged Commodities) Rules. A non-compliant pack may be rejected on arrival at the supplier's cost.

**5.3 Short delivery.** A shortfall is reconciled within 24 hours of delivery. A credit note is issued within 7 days. Repeated short delivery is a performance issue under clause 7.

## 6. Data

Message content exchanged under these terms is used to plan and review fulfilment. Personal contact details are not extracted by the distributor's intake system; see POL-DAT-004.

## 7. Performance review

Delay frequency, short-delivery frequency and quote stability are reviewed monthly. A supplier with three late notices in a month is reviewed before the next allocation cycle. Review does not change the ranking rule for an individual decision.
