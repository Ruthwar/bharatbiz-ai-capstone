---
document_id: POL-SUB-003
title: Product Substitution and Equivalence Policy
doc_type: policy
version: "1.6"
status: approved
effective_from: 2026-07-15
supersedes: none
owner: Category Operations
classification: synthetic
parties: SUP-002, SUP-003, SUP-004, SUP-005
skus: SKU-001, SKU-002, SKU-003, SKU-004, SKU-005, SKU-006
licence: CC0-1.0 (synthetic text authored for this BharatBiz capstone)
source_url: none
retrieved_on: none
---

# Product Substitution and Equivalence Policy

SIMULATION ONLY. Synthetic policy for an academic capstone; not a real trading rule.

## 1. Purpose

A delay creates pressure to send "something similar". This policy states when a different product may be proposed in place of the ordered one, and when it may not.

## 2. What counts as substitution

- **Pack-size change**: a 5 L tin offered in place of a 1 L pouch of the same product. This is a different SKU. It is a substitution, not a like-for-like delivery.
- **Product change**: a different product in the same category, such as a different rice grade. This is a substitution.
- **Supplier change**: the same SKU bought from a different supplier. This is **not** a substitution. It is an ordinary alternative supplier option and is handled by POL-DLY-001.

## 3. Rules

**R1 - Same SKU by default.** The planner may only meet demand with the ordered SKU or by leaving units unmet. Supplier choice is free; product choice is not.

**R2 - Never convert units silently.** Order quantities are in the unit recorded on the order: kg, litre, piece or case. A pack-size change must not be converted into an equivalent volume and presented as the same order. 5 L of oil in a tin is not "five pouches" for ordering purposes.

**R3 - Retailer consent is required.** Any substitution must be disclosed to the retailer and accepted by them before it is planned. Consent cannot be inferred from a general willingness to accept late delivery.

**R4 - Substitution must be visible.** A review card that proposes a substitution must name both SKUs, both pack descriptions, the quantity offered and the reason. It must never be buried in an assumption line.

**R5 - Price and tax differences are shown.** A substitute may carry a different unit cost and a different GST rate. Both are shown to the reviewer. See REG-GST-2025-09.

**R6 - No substitution under delay pressure alone.** A supplier's capacity or a retailer's urgency is not consent. If the ordered SKU cannot be sourced, the correct outcome is unmet units plus human triage, not a silent swap.

## 4. Current system scope

The supplier-delay slice does not model substitutions as candidate plans. A message that proposes one is acknowledged as received and routed to human triage with the proposal attached. This is deliberate: the honest failure mode is escalation, not an unauthorised swap.

## 5. Examples

- A supplier offers 5 L tins instead of 1 L pouches for the same oil: substitution, escalate for consent.
- A second supplier has the same 1 L pouch at a higher rate: normal alternative, rank under POL-DLY-001.
- A supplier offers "46 litres, mixed packs": partial and mixed, escalate under SOP-SHT-003.
