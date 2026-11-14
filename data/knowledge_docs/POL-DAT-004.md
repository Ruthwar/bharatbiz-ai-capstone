---
document_id: POL-DAT-004
title: Evidence, Consent and Data Minimisation Policy
doc_type: policy
version: "2.0"
status: approved
effective_from: 2026-05-20
supersedes: POL-DAT-004 v1.2 (2025-12-01)
owner: Data Governance
classification: synthetic
parties: all
skus: all
licence: CC0-1.0 (synthetic text authored for this BharatBiz capstone)
source_url: none
retrieved_on: none
---

# Evidence, Consent and Data Minimisation Policy

SIMULATION ONLY. Synthetic policy for an academic capstone; not legal advice.

## 1. Purpose

The system quotes a message to justify a decision. This policy defines what may be quoted, what may be stored, and what a retrieval citation may contain.

## 2. Evidence rules

**R1 - Verbatim only.** A fact is recorded with the exact substring of the message and its character offsets. The validator checks that the stored span equals the quoted text. Paraphrase is not evidence.

**R2 - No inference beyond the text.** "Two-day delay" yields a delay of two days and nothing else. A revised date that is not stated is recorded as unknown, never estimated from the delay.

**R3 - Offsets travel with the fact.** A reviewer can locate every field in the original message. If offsets and text disagree, the item is rejected rather than repaired.

**R4 - Catalogue authority.** A SKU mentioned in a message must resolve to the product catalogue. An unresolved product name is an ambiguity, and ambiguity goes to triage.

## 3. Data minimisation

**R5 - Do not collect what the decision does not need.** Retailer phone numbers, delivery addresses, personal names of individuals and bank details are not required to plan a delay. If they appear in a message, they are not extracted, not indexed and not shown in the review card.

**R6 - Approved documents only.** Retrieval indexes only reference documents listed in the corpus manifest. Inbound messages, retailer records and pilot data are never indexed as knowledge.

**R7 - Synthetic by default.** The demo data is labelled synthetic. Real retailer or supplier data must not be sent to an external model endpoint without documented authorisation.

**R8 - Retention.** The demo ledger keeps inbound results and review items for 30 days or until reset. Reset clears results, intakes and the review queue together.

## 4. Retrieval-specific rules

**R9 - Citations carry provenance.** Every retrieved section carries its document id, title, effective date, licence and, for regulatory material, the source URL and retrieval date. A citation without provenance is a defect.

**R10 - Retrieval supplies text, never numbers.** Policy text may explain a rule or a threshold. It must not be used to compute a quantity, price, tax or arrival date. Those come from the versioned business state and deterministic code.

**R11 - Quote, do not summarise.** The review card shows the retrieved section text or an exact sentence from it, not a model-written paraphrase. This keeps the reviewer's check honest.

## 5. Why this matters

A decision-support tool that quotes an unverified sentence is worse than one that quotes nothing, because the quote borrows authority it has not earned. Provenance and verbatim spans are what make the citation checkable.
