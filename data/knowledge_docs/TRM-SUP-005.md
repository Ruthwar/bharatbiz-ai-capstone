---
document_id: TRM-SUP-005
title: Supplier Terms - Sri Venkateswara FMCG Supply (SUP-005)
doc_type: supplier_terms
version: "3.0"
status: approved
effective_from: 2026-08-20
supersedes: TRM-SUP-005 v2.6 (2026-01-05)
owner: Procurement
classification: synthetic
parties: SUP-005
skus: SKU-002, SKU-003, SKU-004, SKU-005, SKU-007, SKU-008, SKU-010, SKU-011, SKU-012
licence: CC0-1.0 (synthetic text authored for this BharatBiz capstone)
source_url: none
retrieved_on: none
---

# Supplier Terms - Sri Venkateswara FMCG Supply

SIMULATION ONLY. Synthetic supplier terms for an academic capstone. Sri Venkateswara FMCG Supply is a fictional party.

## 1. Commercial summary

| Item | Term |
| --- | --- |
| Supplier id | SUP-005 |
| Lead time | 1 day from confirmed order |
| Payment terms | 7 days from delivery |
| Quote validity | 7 days from issue |
| Delay notice | Immediately on becoming aware |
| Short-delivery credit note | 7 days from reconciliation |

## 2. Ordering

**2.1 Minimum order quantity.** Per line: 1 unit for Rice 10 kg bag and Soap case; 5 units for Cooking oil 5 L tin and Biscuits family carton; 10 units for Cooking oil 1 L pouch, Shampoo sachet carton, Beverage crate, Detergent case and Toothpaste case.

**2.2 Capacity.** Capacity is committed per SKU per cycle in the supplier offer. The distributor does not assume spare capacity.

**2.3 Same-day window.** Orders confirmed before 11:00 are dispatched the same working day; later orders dispatch the next working day. One-day lead time assumes confirmation inside the window.

## 3. Delivery and delay

**3.1 Lead time.** One day. Because the lead time is short, a delay notice usually means the order will miss the retailer's requested date.

**3.2 Delay notice.** This supplier must notify immediately on becoming aware of a delay, and in any case before the dispatch window closes. Notice after dispatch is treated as a delivery failure, not a delay notice.

**3.3 Revised date.** The notice must state a revised date. Where the supplier writes that the revised date is **not confirmed**, the planner records the date as unknown and must not infer one from the stated delay length. This is the normal case in the demo scenario.

**3.4 Cancellation.** The distributor may cancel an unconfirmed line within 48 hours of order without penalty.

## 4. Price

**4.1 Quote validity.** Seven days from issue. A rate used in an approved plan after expiry must be re-confirmed.

**4.2 Mid-delay price change.** A rate change during a delay must be notified in writing before dispatch. The current intake system does not parse a rate change inside a delay message; such a message is routed to human triage. Do not assume the old rate is protected.

**4.3 Taxes.** Rates exclude GST. GST is charged at the rate applicable on the invoice date under REG-GST-2025-09.

## 5. Partial dispatch

This supplier may dispatch part of a line and the remainder later with 24 hours' notice. The distributor's planner does not model split arrivals; a partial dispatch notice is triaged under SOP-SHT-003 and split manually into line-level records.

## 6. Quality and labelling

**6.1 Food and non-food.** Food SKUs must meet FSSAI labelling requirements (REG-FSSAI-LAB-2020). All packaged SKUs must meet the Legal Metrology declarations for net quantity, retail sale price and consumer care (REG-LMPC-2011-R6).

**6.2 Damage in transit.** Damaged units are replaced or credited. Units are not counted as delivered for planning until they are accepted at the depot.

**6.3 Rejection.** A rejected line is a new fact for planning. It does not silently reduce the order.
