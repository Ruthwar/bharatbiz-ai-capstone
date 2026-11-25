"""Generate the additive Track B synthetic knowledge corpus.

The canonical 33-document corpus in data/knowledge_docs/ is the runtime source of truth and is
never touched. This script writes 480 clearly-labelled synthetic documents into
data/knowledge_docs_track_b/ so retrieval experiments can be measured on a larger, realistic
distributor corpus without changing what the demo cites.

Every generated document is subordinate to the distributor-wide policy. Where an addendum,
circular, case note or quick-reference note appears to conflict with a canonical document, the
canonical document prevails. Nothing here is a real policy, supplier term or regulatory extract.

Usage:
    python scripts/build_track_b_corpus.py --write
    python scripts/build_track_b_corpus.py --check
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = PROJECT_ROOT / "data" / "knowledge_docs_track_b"
BASE_DIR = PROJECT_ROOT / "data" / "knowledge_docs"

SEED = 20261124
GENERATED_ON = "2026-11-24"
EXPECTED_DOCUMENTS = 480

AREAS = (
    ("AME", "Ameerpet"),
    ("DIL", "Dilsukhnagar"),
    ("KUK", "Kukatpally"),
    ("SEC", "Secunderabad"),
)

CATEGORIES = (
    ("RICE", "Rice", "SKU-001, SKU-002"),
    ("OIL", "Cooking oil", "SKU-003, SKU-004"),
    ("BISC", "Biscuits", "SKU-005, SKU-006"),
    ("SOAP", "Soap", "SKU-007"),
    ("SHMP", "Shampoo", "SKU-008"),
    ("TEA", "Tea", "SKU-009"),
    ("BEV", "Beverage", "SKU-010"),
    ("DET", "Detergent", "SKU-011"),
    ("PASTE", "Toothpaste", "SKU-012"),
    ("PULSE", "Pulses", "SKU-001, SKU-003"),
    ("SPICE", "Spices", "SKU-009, SKU-012"),
    ("SNACK", "Snack foods", "SKU-005, SKU-010"),
)

SUPPLIERS = (
    ("SUP-001", "Shree Ganesh Trading Co"),
    ("SUP-002", "Balaji Wholesale Distributors"),
    ("SUP-003", "Krishna Rice Mills"),
    ("SUP-004", "Anand Oil Agencies"),
    ("SUP-005", "Godavari FMCG Supply"),
)

POLICY_FAMILIES = (
    (
        "DLY",
        "Supplier delay response",
        "unconfirmed arrival dates, partial deliveries and re-planning",
        (
            "An arrival date that the supplier has only described verbally is recorded as unknown in {area}; staff do not turn it into a promise.",
            "A partial delivery is counted against the open order before any replacement quantity is discussed with the retailer.",
            "Re-planning is triggered by a cancellation, a confirmed date change, a quantity change or a price change and not by elapsed time alone.",
            "The stock-only plan stays visible in {area} so the reviewer can compare buying against waiting.",
            "Escalation to the area operations lead is required when the affected units cross the zone threshold recorded in the weekly exception list.",
            "Anyone who cannot reconcile the delayed units against the current state version stops and asks for triage instead of estimating.",
        ),
    ),
    (
        "STK",
        "Stock count and reservation",
        "count freezes, reserved stock, damaged stock and adjustment approval",
        (
            "Counted stock in {area} is not usable until the count is approved; a pending count cannot be promised against an order.",
            "Reserved units belong to other orders and are never reallocated during a shortage conversation.",
            "Damaged units are moved to the hold location before the count sheet is closed, with the reason written on the sheet.",
            "A negative variance larger than the zone tolerance is investigated before the count is posted.",
            "Every adjustment carries the counter name, the approver name and the reason code in the audit trail.",
            "Stock that is physically present but not yet receipted is recorded separately and never merged into available stock.",
        ),
    ),
    (
        "CSH",
        "Cash and liquidity",
        "cash buffers, projected outflows, receivables and credit limits",
        (
            "A candidate plan is excluded in {area} when projected ending cash falls below the minimum buffer, even if it ranks first on service.",
            "Supplier payment terms change when cash leaves the account, not when the invoice is printed.",
            "A scheduled receivable that has not been confirmed is treated as uncertain and is not used to justify an extra purchase.",
            "The area lead records the cash assumption used in a review so the reviewer can reproduce the projection.",
            "Credit-limit exceptions are routed to finance and are never approved by the person who wants the purchase.",
            "Cash projections in {area} use the same state version as the plan under review and never mix versions.",
        ),
    ),
    (
        "SUB",
        "Product substitution",
        "pack-size changes, alternative SKUs and retailer consent",
        (
            "A different pack size is a substitution in {area} and needs the retailer's recorded consent before it is planned.",
            "A different SKU is never presented as the same product, even when the category and brand match.",
            "Substitution is offered only after the original line is confirmed unavailable or undeliverable within the horizon.",
            "The consent record stores who agreed, when, and which pack or SKU replaced the original.",
            "Refused substitution returns the line to the original product and routes the case for triage.",
            "Price differences caused by substitution are shown to the reviewer and are not hidden inside an average.",
        ),
    ),
    (
        "PRC",
        "Price and scheme changes",
        "rate cards, trade schemes, claim windows and price disputes",
        (
            "A revised rate card applies from its written effective date in {area} and not from the date the message is read.",
            "A scheme claim outside its claim window is rejected with the reason and the window printed on the rejection note.",
            "The approved rate card is the only source for pricing a candidate plan; a verbal price is never used.",
            "A price dispute pauses the affected line until the rate card owner confirms the correct version.",
            "Scheme quantities are calculated from the eligible invoices and not from the retailer's summary message.",
            "Any back-dated correction needs sign-off from the commercial owner and is recorded as a correction, not a new claim.",
        ),
    ),
    (
        "RCM",
        "Retailer complaint handling",
        "intake, missing order references, follow-up rounds and triage",
        (
            "A complaint that arrives without an order reference is preserved in {area} and the missing fact is requested once.",
            "Only decision-relevant facts are requested; the intake desk does not ask for information it already holds.",
            "A complaint that cannot be matched after the allowed follow-up rounds goes to human triage with the full transcript.",
            "The retailer is never told that a claim is approved before a person has recorded the decision.",
            "Duplicate complaints are linked to the first ticket instead of opening a second queue entry.",
            "Every complaint keeps the original wording so the reviewer can see what the retailer actually said.",
        ),
    ),
    (
        "MSC",
        "Market signal corroboration",
        "independent sources, scope matching and demand signals",
        (
            "A single forwarded message is a lead in {area} and not a confirmed market signal.",
            "Copies, forwards and screenshots of the same report count as one source, however many times they arrive.",
            "Corroborating sources must describe the same product, area and time window before they are combined.",
            "A market signal may adjust a forecast assumption but never bypasses the demand simulation record.",
            "Conflicting signals are shown side by side and are escalated rather than averaged silently.",
            "The source, retrieval date and scope of each signal are recorded with the demand review.",
        ),
    ),
    (
        "DEM",
        "Demand and promotion planning",
        "uplift assumptions, promotion calendars and simulation records",
        (
            "A promotion uplift in {area} is recorded as an explicit percentage and never as an unspoken adjustment.",
            "A demand simulation records its baseline, horizon, assumptions and outputs so it can be reproduced.",
            "Promotion stock is not promised to a retailer until the uplift assumption has been reviewed.",
            "A forecast that contradicts the latest approved plan is flagged instead of being applied quietly.",
            "Uplift assumptions are versioned with the promotion calendar they belong to.",
            "A repeated promotion is simulated again when the category, area or price basis changes.",
        ),
    ),
    (
        "SVC",
        "Service credits and fill rate",
        "fill rate, service credits and delivery acknowledgement",
        (
            "A service credit is calculated from the acknowledged delivery record in {area}, not from the retailer's estimate.",
            "Fill rate is measured against the confirmed order line and is not adjusted after the fact.",
            "A credit note is issued only after the delivery discrepancy is verified against the evidence.",
            "Repeated service failures in one area are reviewed weekly with the supplier owner.",
            "The reviewer sees the credit calculation and its basis before approving the resolution.",
            "A credit recorded against the wrong invoice is reversed by correction and not by a second credit.",
        ),
    ),
    (
        "RCL",
        "Recall and expiry control",
        "batch recalls, near-expiry stock and dispatch blocks",
        (
            "Any batch named in a recall notice is blocked from dispatch in {area} as soon as the notice is received.",
            "Near-expiry stock is flagged with its remaining shelf life before it is offered against an order.",
            "A recall pickup is recorded separately from a routine return and is reconciled against the notice quantity.",
            "Stock covered by a recall is never substituted for a customer order.",
            "The recall log records the notice reference, the affected batch and the person who blocked the stock.",
            "An expired batch found on the shelf triggers a count of the same batch in every area location.",
        ),
    ),
)

SOP_OPERATIONS = (
    (
        "INT",
        "Inbound intake",
        (
            "Open the message in the intake workspace and keep the original wording unchanged.",
            "Check whether the sender, order reference and product are already known before asking the retailer anything.",
            "Ask at most one round of questions, limited to the facts that change the decision.",
            "Record the outcome as a review case, a clarification request or human triage.",
        ),
    ),
    (
        "PICK",
        "Stock rotation and picking",
        (
            "Pick the earliest approved batch first unless a recall or expiry block applies.",
            "Confirm the pick quantity against reserved stock before releasing the line.",
            "Mark short picks with the reason code instead of silently reducing the quantity.",
            "Return unpicked units to their recorded location before the shift closes.",
        ),
    ),
    (
        "LOAD",
        "Dispatch load plan",
        (
            "Build the load plan from confirmed order lines only.",
            "Check the route sequence and the vehicle capacity before locking the plan.",
            "Keep recall-blocked and near-expiry stock off the load sheet.",
            "Record the dispatcher, the vehicle and the locked time on the load sheet.",
        ),
    ),
    (
        "SHELF",
        "Shelf-life and quality check",
        (
            "Check remaining shelf life against the category minimum before offering the batch.",
            "Separate damaged or leaking packs at the quality point and record the quantity.",
            "Quarantine any batch with an unclear date code until the supplier owner confirms it.",
            "Log the check result against the batch, not only against the order.",
        ),
    ),
    (
        "RET",
        "Returns and reconciliation",
        (
            "Record the return reason and the original invoice reference before accepting stock back.",
            "Count returned units in the presence of the delivery person where the process allows it.",
            "Reconcile the return against the credit note and raise a discrepancy if the quantities differ.",
            "Return recalled stock through the recall log rather than the routine returns flow.",
        ),
    ),
)

SUPPLIER_SERIES = (
    ("Ordering", "minimum order quantity and order confirmation"),
    ("Delivery", "lead time, split delivery and acknowledgement"),
    ("Pricing", "rate card, invoice matching and price disputes"),
    ("Credit", "payment terms, credit notes and claim windows"),
    ("Quality", "damaged cartons, short delivery and returns"),
    ("Service", "fill rate, service credits and review cadence"),
    ("Forecast", "forecast sharing and promotion volumes"),
    ("Escalation", "contacts, response times and exception review"),
)

CASE_THEMES = (
    (
        "late delivery escalation",
        (
            "A supplier told the desk that part of an order would slip past the requested date and would not put the new timing in writing.",
            "The inbound note said several cases would arrive late; the sender could not confirm a written arrival slot.",
        ),
        (
            "The desk compared the affected units with usable stock and the orders due inside the horizon before discussing any option.",
            "The desk reconciled the delayed quantity with the current state version and the open orders, then listed the choices.",
        ),
        (
            "The timing stayed an unknown, the reviewer weighed buying against waiting, and the retailer heard only the reviewed outcome.",
            "The case went to a reviewer with the arrival recorded as unknown; no promise left the desk that day.",
        ),
        (
            "A verbal estimate is not a written arrival commitment.",
            "Silence on the exact timing is still an unknown, not a licence to guess.",
        ),
    ),
    (
        "short delivery claim",
        (
            "A retailer claimed a delivered case was twelve units light while the delivery sheet showed a full case.",
            "The shop reported fewer units than the dispatch note listed and asked for a credit the same day.",
        ),
        (
            "The desk checked the delivery evidence, the pick sheet and the acknowledgement before opening a credit review.",
            "The desk matched the claim to the signed acknowledgement and the warehouse pick record.",
        ),
        (
            "The gap was confirmed against the evidence and routed to a person for the credit decision.",
            "The case was held for human review because the paperwork and the claim did not agree.",
        ),
        (
            "A claim without evidence is a lead, not a confirmed shortage.",
            "The signed acknowledgement decides a short-delivery dispute, not the loudest account of it.",
        ),
    ),
    (
        "damaged carton claim",
        (
            "Several cartons arrived crushed and the retailer sent photographs the same evening.",
            "The shop refused two leaking cases at the door and kept the damaged packs for inspection.",
        ),
        (
            "The desk matched the photographs to the delivery reference and recorded the damaged quantity at the quality point.",
            "The desk linked the refused cases to the load sheet and counted the damaged units at the returns dock.",
        ),
        (
            "The damaged units were quarantined and the replacement line waited for an approved count.",
            "The hold was posted and the replacement was planned only after the count was signed off.",
        ),
        (
            "Damaged stock stays out of available stock until the count is posted.",
            "A photograph supports a claim; an approved count changes the stock position.",
        ),
    ),
    (
        "price revision dispute",
        (
            "A retailer disputed an invoice because the rate was higher than the figure quoted the previous week.",
            "The shop said the billed rate did not match the rate card it had been shown at the counter.",
        ),
        (
            "The desk checked the approved rate card and its effective date before responding.",
            "The desk compared the invoice date with the version of the rate card in force that day.",
        ),
        (
            "The new rate applied from its written effective date and the invoice was explained with the card reference.",
            "The invoice stood because the rate card allowed it; the earlier counter quote was recorded as informal.",
        ),
        (
            "A verbal price quote never overrides the approved rate card.",
            "The effective date on the card settles a price argument.",
        ),
    ),
    (
        "scheme claim rejection",
        (
            "A scheme claim arrived after the claim window had closed but the retailer said the invoices were genuine.",
            "The shop submitted a trade-scheme claim late and argued that the qualifying bills were real.",
        ),
        (
            "The desk checked the eligible invoices and the claim window printed on the scheme circular.",
            "The desk checked the claim date against the circular and the invoice dates against the eligibility rule.",
        ),
        (
            "The claim was rejected with the reason and the window stated clearly on the rejection note.",
            "The claim was returned with the closing date quoted; no exception was granted at the desk.",
        ),
        (
            "A genuine invoice does not extend a closed claim window.",
            "A late claim is late even when the underlying bill is real.",
        ),
    ),
    (
        "credit note follow-up",
        (
            "A retailer asked for the status of a credit note promised during an earlier complaint.",
            "The shop called again about a credit that had been discussed but never seen on its account.",
        ),
        (
            "The desk checked the complaint ticket, the verification record and the credit register.",
            "The desk traced the earlier ticket and compared it with the posted credit entries.",
        ),
        (
            "The status came from the register and the retailer received the recorded outcome rather than a new promise.",
            "The desk confirmed that nothing had been posted and routed the gap for human review.",
        ),
        (
            "A promised credit is not a posted credit until it appears in the register.",
            "Check the register before repeating a promise made on a call.",
        ),
    ),
    (
        "near-expiry batch",
        (
            "A batch of biscuits had less than one third of its shelf life left and was still shown as available.",
            "The picker found shampoo sachets close to their date code in the forward location.",
        ),
        (
            "The desk checked the batch date code against the category minimum before the line was offered.",
            "The desk compared remaining shelf life with the category threshold and the order due date.",
        ),
        (
            "The batch was flagged, blocked from the offer and routed for a disposal or return review.",
            "The line was held back and the batch went to the quality review.",
        ),
        (
            "Available quantity and offerable quantity are not the same number.",
            "A date code check happens before an offer, not after a complaint.",
        ),
    ),
    (
        "recall pickup",
        (
            "A recall notice named one batch that had already left the warehouse on two routes.",
            "The supplier withdrew a batch after part of it had been loaded for delivery.",
        ),
        (
            "The desk blocked the batch, identified the affected deliveries and recorded the pickup separately from routine returns.",
            "The desk froze the date code, traced the load sheets and opened a recall log entry.",
        ),
        (
            "The pickup was reconciled against the notice quantity and the recall log was signed off.",
            "The returned units were counted against the notice and the log was closed with a name.",
        ),
        (
            "Recall stock is never substituted for a customer order.",
            "A recall is a block, not a reason to re-offer the same goods.",
        ),
    ),
    (
        "substitution refusal",
        (
            "A retailer refused a five litre tin offered in place of a one litre pouch during a shortage.",
            "The shop rejected an alternative pack size proposed while its usual pack was unavailable.",
        ),
        (
            "The desk checked that consent had not been recorded and returned the line to the original product.",
            "The desk confirmed no recorded agreement and put the original line back on the plan.",
        ),
        (
            "The refusal was recorded, the line was re-planned and the reviewer saw the original product on the card.",
            "The rejection was logged and the case returned to review with the requested pack unchanged.",
        ),
        (
            "A pack-size change is a substitution and needs recorded consent.",
            "Offering a different pack is a proposal, not a fulfilment of the same line.",
        ),
    ),
    (
        "market rumour check",
        (
            "Two retailers forwarded the same market report claiming a price rise for tea in the coming month.",
            "Three shops shared the same screenshot about a spice shortage next week.",
        ),
        (
            "The desk treated the forwards as one source and looked for an independent, scope-matched signal.",
            "The desk traced the screenshot to a single report and searched for separate evidence in the same area.",
        ),
        (
            "The signal stayed a lead and did not change the demand assumption used in the review.",
            "No independent source appeared, so the forecast assumption was left as it was.",
        ),
        (
            "Forwards of one report are one source, not corroboration.",
            "A screenshot repeated three times is still one screenshot.",
        ),
    ),
)

CIRCULAR_TOPICS = (
    (
        "count freeze windows",
        "Counts pause during the month-end freeze window so the closing stock position is not disturbed by mid-count adjustments.",
        "Area leads publish the freeze timetable, and any count started after the freeze begins is held until the window closes.",
    ),
    (
        "reserved stock protection",
        "Reserved units belong to specific open orders and must not be released during a shortage conversation.",
        "The reviewer sees reserved and available quantities separately on every plan card.",
    ),
    (
        "cash buffer escalation",
        "Any plan that would push projected ending cash below the buffer is escalated before it is presented to a reviewer.",
        "The escalation note records the plan id, the projected closing cash and the assumption behind the outflow.",
    ),
    (
        "scheme circular filing",
        "Every trade scheme circular is filed against its claim window and its eligible categories.",
        "Claims are checked against the filed circular and not against a retailer's summary of it.",
    ),
    (
        "rate card updates",
        "Rate cards take effect from the date printed on the approved card.",
        "Staff replace the previous card in the pricing workspace instead of keeping two live versions.",
    ),
    (
        "complaint triage rota",
        "Complaints that need a decision after intake are assigned to the daily triage rota.",
        "The rota owner closes or re-routes the ticket the same working day where possible.",
    ),
    (
        "route change notices",
        "Route changes are published before the lock time of the load plan.",
        "A late route change is recorded as an exception and reviewed with the transport owner.",
    ),
    (
        "returns dock hygiene",
        "Returned stock is separated by reason before it re-enters available stock.",
        "Damaged, recalled and routine returns use different hold locations.",
    ),
    (
        "document retention",
        "Intake messages, decision records and approval reasons are retained with their state versions.",
        "Staff do not edit a retained record; corrections are added as new records.",
    ),
    (
        "supplier escalation contacts",
        "Each supplier has a named escalation contact and a response expectation.",
        "Repeated misses are reviewed weekly with the supplier owner.",
    ),
    (
        "weekly exception review",
        "The area team reviews open exceptions, repeated complaints and unresolved decisions every week.",
        "The review records owners and due dates and does not close an exception without evidence.",
    ),
)

TRAINING_TOPICS = (
    (
        "reading a plan card",
        "A plan card shows the selected mode, the chosen candidate, the verified outcomes and the policy basis.",
        "Read the mode first, then the verified outcomes, then the cost and service difference before forming a view.",
        "Do not assume the cheapest candidate is the recommended one; affordability is checked before ranking.",
    ),
    (
        "recording a stock count",
        "Counts are recorded against the current state version and are not usable until approved.",
        "Write the counter name, the reason for any adjustment and the hold location for damaged stock.",
        "Do not merge receipted and unreceipted stock into one available figure.",
    ),
    (
        "raising a complaint ticket",
        "A complaint is preserved exactly as received and matched to an order where possible.",
        "Ask only for the facts that change the decision, then route the ticket.",
        "Do not tell the retailer that a claim is approved before a person has decided.",
    ),
    (
        "checking policy dates",
        "A policy applies from its effective date and only to the parties named in its metadata.",
        "Check the document version and effective date against the decision date.",
        "Do not apply a policy that is still pending or out of scope for the party.",
    ),
    (
        "handling a missing order reference",
        "A missing order reference is a clarification point, not a reason to discard the message.",
        "Keep the original message, request the reference once and continue with the known facts.",
        "Do not invent an order reference from a similar retailer name.",
    ),
    (
        "logging a market lead",
        "A market signal is logged with its source, date and scope.",
        "Look for an independent, scope-matched source before treating it as corroboration.",
        "Do not count forwards or copies as separate sources.",
    ),
    (
        "using deterministic mode",
        "Deterministic mode ranks eligible candidates by the fixed rule order.",
        "Use it when you need a reproducible result for review or audit.",
        "Do not silently switch modes when a grounded result is unavailable.",
    ),
    (
        "citing a policy quote",
        "A citation must quote the retrieved passage and carry its document version and effective date.",
        "Prefer the rule section over an overview paragraph when citing a decision basis.",
        "Do not paraphrase a rule into a stronger promise than the text supports.",
    ),
    (
        "recording a human decision",
        "A human decision records the approver, the decision and the reason.",
        "Approval changes the review state only; it does not execute a purchase, payment or message.",
        "Do not reuse an approval from a different state version.",
    ),
    (
        "closing an intake case",
        "An intake case closes when the decision, clarification or triage outcome is recorded.",
        "Check that the transcript and the decision record are linked before closing.",
        "Do not close a case by deleting the message or the review record.",
    ),
    (
        "avoiding duplicate ledger entries",
        "Every intake event is recorded once with its state version and source.",
        "Check for an existing ticket before creating a new one for a forwarded message.",
        "Do not rewrite a ledger record to hide a duplicate; link the records instead.",
    ),
)


def _effective_date(index: int) -> str:
    year = 2025 + (index % 2)
    month = 1 + (index * 3) % 10
    day = 1 + (index * 7) % 27
    return f"{year}-{month:02d}-{day:02d}"


def _version(index: int) -> str:
    return f"{1 + index % 4}.{index % 5}"


def _preamble(kind: str) -> str:
    return (
        f"SIMULATION ONLY. This is a synthetic {kind} written for the BharatBiz academic capstone. "
        "It is not a real distributor policy, supplier agreement or regulatory extract. "
        "Every party, amount and reference is fictional. This document is subordinate to the "
        "distributor-wide policy; where the two appear to differ the distributor-wide policy prevails."
    )


def _render(
    *,
    document_id: str,
    title: str,
    doc_type: str,
    effective_from: str,
    version: str,
    owner: str,
    sections: list[tuple[str, str]],
    parties: str = "all",
    skus: str = "",
    kind: str,
) -> str:
    lines = [
        "---",
        f"document_id: {document_id}",
        f"title: {title}",
        f"doc_type: {doc_type}",
        f'version: "{version}"',
        "status: approved",
        f"effective_from: {effective_from}",
        "supersedes: none",
        f"owner: {owner}",
        "classification: synthetic",
        f"parties: {parties}",
        f"skus: {skus}" if skus else "skus: none",
        "licence: CC0-1.0 (synthetic text authored for this BharatBiz capstone)",
        "source_url: none",
        "retrieved_on: none",
        "---",
        "",
        f"# {title}",
        "",
        _preamble(kind),
    ]
    for heading, body in sections:
        lines.extend(["", f"## {heading}", "", body])
    return "\n".join(lines) + "\n"


def _addenda(rng: random.Random) -> list[tuple[str, str]]:
    documents = []
    index = 0
    for area_code, area_name in AREAS:
        for family_code, family_title, family_scope, rules in POLICY_FAMILIES:
            index += 1
            chosen = rng.sample(rules, k=3)
            local_rules = "\n".join(f"- {rule.format(area=area_name)}" for rule in chosen)
            documents.append(
                (
                    f"TB-ADD-{family_code}-{area_code}",
                    _render(
                        document_id=f"TB-ADD-{family_code}-{area_code}",
                        title=f"{area_name} Area Addendum - {family_title}",
                        doc_type="policy",
                        effective_from=_effective_date(index),
                        version=_version(index),
                        owner=f"{area_name} Area Operations",
                        parties=f"AREA-{area_code}",
                        kind="area policy addendum",
                        sections=[
                            (
                                "Local operating context",
                                f"This addendum describes how the {area_name} team applies the {family_title.lower()} "
                                f"policy to {family_scope}. It exists because the {area_name} route pattern and the "
                                "local retailer mix create recurring questions that the distributor-wide policy answers "
                                "only at a general level.",
                            ),
                            ("Local operating rules", local_rules),
                            (
                                "Precedence",
                                "This addendum is subordinate to the distributor-wide policy and to any approved "
                                "supplier terms. Where an addendum appears to conflict with a canonical policy or a "
                                "supplier term, the canonical document prevails and the conflict is logged for the "
                                "policy owner.",
                            ),
                            (
                                "Review and audit",
                                f"The {area_name} area lead reviews this addendum each quarter. Each review records "
                                "the documents in force, the exceptions raised since the last review and any proposed "
                                "change. No operational action, payment, price change or outbound message is "
                                "authorised by this addendum.",
                            ),
                        ],
                    ),
                )
            )
    return documents


def _category_sops(rng: random.Random) -> list[tuple[str, str]]:
    documents = []
    index = 100
    for category_code, category_name, skus in CATEGORIES:
        for operation_code, operation_name, steps in SOP_OPERATIONS:
            index += 1
            chosen = rng.sample(steps, k=3)
            numbered = "\n".join(f"{position}. {step}" for position, step in enumerate(chosen, start=1))
            documents.append(
                (
                    f"TB-SOP-{category_code}-{operation_code}",
                    _render(
                        document_id=f"TB-SOP-{category_code}-{operation_code}",
                        title=f"SOP - {operation_name} for {category_name}",
                        doc_type="sop",
                        effective_from=_effective_date(index),
                        version=_version(index),
                        owner="Warehouse Operations",
                        parties="all",
                        skus=skus,
                        kind="operating procedure",
                        sections=[
                            (
                                "Purpose and scope",
                                f"This procedure explains how the warehouse team performs {operation_name.lower()} "
                                f"for the {category_name} category. It applies to the SKUs listed in the document "
                                "metadata and to any pack size derived from them.",
                            ),
                            ("Steps", numbered),
                            (
                                "Records",
                                "The operator records the state version, the quantity, the reason code and the "
                                "approver for every exception. Records are retained with the intake or dispatch "
                                "reference so a reviewer can reconstruct the action.",
                            ),
                            (
                                "Escalation",
                                "If the steps cannot be completed against the current state version, the operator "
                                "stops and raises the case for triage. The operator does not estimate a quantity, "
                                "reallocate reserved stock or release recalled stock to keep the workflow moving.",
                            ),
                        ],
                    ),
                )
            )
    return documents


def _supplier_terms(rng: random.Random) -> list[tuple[str, str]]:
    documents = []
    index = 200
    for supplier_index, (supplier_id, supplier_name) in enumerate(SUPPLIERS, start=1):
        for series_index, (series_name, series_focus) in enumerate(SUPPLIER_SERIES, start=1):
            index += 1
            category = CATEGORIES[(series_index + supplier_index) % len(CATEGORIES)]
            category_name, skus = category[1], category[2]
            documents.append(
                (
                    f"TB-TRM-{supplier_index:02d}-{series_index}",
                    _render(
                        document_id=f"TB-TRM-{supplier_index:02d}-{series_index}",
                        title=f"Supplier Terms Addendum - {supplier_name} - {series_name}",
                        doc_type="supplier_terms",
                        effective_from=_effective_date(index),
                        version=_version(index),
                        owner="Procurement",
                        parties=supplier_id,
                        skus=skus,
                        kind="supplier terms addendum",
                        sections=[
                            (
                                "Commercial basis",
                                f"This addendum records the {series_name.lower()} expectations agreed with "
                                f"{supplier_name} ({supplier_id}) for {series_focus}. It applies to {category_name} "
                                "lines in the current catalogue unless a category-specific addendum says otherwise.",
                            ),
                            (
                                "Operating terms",
                                f"- Order confirmation is written and states the confirmed quantity and the earliest "
                                f"despatch date.\n- A {series_name.lower()} exception is raised within the agreed "
                                f"response window.\n- The approved rate card is the reference for pricing and claim "
                                f"calculation.\n- Unconfirmed dates are recorded as unknown and are never presented to "
                                f"a retailer as a promise.",
                            ),
                            (
                                "Claims and disputes",
                                "A claim is raised against the verified delivery or invoice record and never against "
                                "a summary message. A dispute pauses the affected line until the commercial owner "
                                "confirms the correct document version.",
                            ),
                            (
                                "Precedence",
                                "These terms are subordinate to the distributor-wide policies on cash, stock, "
                                "substitution and recall. They do not authorise a purchase, a payment or an outbound "
                                "message.",
                            ),
                        ],
                    ),
                )
            )
    return documents


def _case_notes(rng: random.Random) -> list[tuple[str, str]]:
    documents = []
    for index in range(1, 121):
        theme_name, situations, checked_variants, outcomes, lessons = CASE_THEMES[(index - 1) % len(CASE_THEMES)]
        situation = rng.choice(situations)
        checked = rng.choice(checked_variants)
        outcome = rng.choice(outcomes)
        lesson = rng.choice(lessons)
        category = CATEGORIES[(index * 5) % len(CATEGORIES)]
        area_code, area_name = AREAS[index % len(AREAS)]
        retailer_id = f"RET-{(index % 20) + 1:03d}"
        documents.append(
            (
                f"TB-CASE-{index:03d}",
                _render(
                    document_id=f"TB-CASE-{index:03d}",
                    title=f"Case Note - {theme_name.title()} in {area_name} ({category[1]})",
                    doc_type="case_note",
                    effective_from=_effective_date(300 + index),
                    version="1.0",
                    owner="Operations Desk",
                    parties=f"{retailer_id}, AREA-{area_code}",
                    skus=category[2],
                    kind="case note",
                    sections=[
                        (
                            "Situation",
                            f"{situation} The case involved {category[1].lower()} lines and retailer "
                            f"{retailer_id} in {area_name}.",
                        ),
                        ("What was checked", checked),
                        ("Outcome", f"{outcome} The reviewer recorded the decision and the reason against the "
                                    "current state version."),
                        ("Lesson", lesson),
                    ],
                ),
            )
        )
    return documents


def _circulars(rng: random.Random) -> list[tuple[str, str]]:
    documents = []
    for index in range(1, 111):
        topic_name, instruction, detail = CIRCULAR_TOPICS[(index - 1) % len(CIRCULAR_TOPICS)]
        area_code, area_name = AREAS[(index // 3) % len(AREAS)]
        documents.append(
            (
                f"TB-CIR-{index:03d}",
                _render(
                    document_id=f"TB-CIR-{index:03d}",
                    title=f"Operations Circular {index:03d} - {topic_name.title()}",
                    doc_type="policy",
                    effective_from=_effective_date(500 + index),
                    version="1.0",
                    owner="Operations Governance",
                    parties=f"AREA-{area_code}",
                    kind="internal circular",
                    sections=[
                        (
                            "Background",
                            f"The {area_name} area team raised repeated questions about {topic_name}. This "
                            "circular records the current instruction so the answer does not depend on who is on "
                            "shift. It restates existing policy and does not create a new entitlement.",
                        ),
                        ("Instruction", instruction),
                        (
                            "Recording",
                            f"{detail} The {area_name} team files this circular under review pack {index:03d} and "
                            "records the date it was briefed to the shift.",
                        ),
                        (
                            "Audit",
                            "The circular owner reviews the instruction every quarter and records any exception "
                            "raised in the area exception list. Circulars are retained with their effective date.",
                        ),
                    ],
                ),
            )
        )
    return documents


def _training_notes(rng: random.Random) -> list[tuple[str, str]]:
    documents = []
    for index in range(1, 111):
        topic_name, what, steps, mistake = TRAINING_TOPICS[(index - 1) % len(TRAINING_TOPICS)]
        category = CATEGORIES[(index * 7) % len(CATEGORIES)]
        documents.append(
            (
                f"TB-TRN-{index:03d}",
                _render(
                    document_id=f"TB-TRN-{index:03d}",
                    title=f"Quick Reference - {topic_name.title()} ({category[1]})",
                    doc_type="sop",
                    effective_from=_effective_date(700 + index),
                    version="1.0",
                    owner="Operations Enablement",
                    parties="all",
                    skus=category[2],
                    kind="training quick reference",
                    sections=[
                        ("When to use this note", what),
                        (
                            "What to do",
                            f"{steps} In the {category[1].lower()} examples used for training, the same step is "
                            "practised with the category manager before the shift.",
                        ),
                        ("Common mistakes", mistake),
                        (
                            "Where the rule lives",
                            "This note is a training aid. The authoritative rule is in the distributor-wide "
                            "policy for the topic, and the policy version and effective date control the decision.",
                        ),
                    ],
                ),
            )
        )
    return documents


def build_documents() -> dict[str, str]:
    rng = random.Random(SEED)
    documents: list[tuple[str, str]] = []
    documents.extend(_addenda(rng))
    documents.extend(_category_sops(rng))
    documents.extend(_supplier_terms(rng))
    documents.extend(_case_notes(rng))
    documents.extend(_circulars(rng))
    documents.extend(_training_notes(rng))

    by_id = {document_id: text for document_id, text in documents}
    if len(by_id) != len(documents):
        raise SystemExit("Generated duplicate document ids")
    if len(documents) != EXPECTED_DOCUMENTS:
        raise SystemExit(f"Expected {EXPECTED_DOCUMENTS} documents, generated {len(documents)}")
    return dict(sorted(by_id.items()))


def build_manifest(documents: dict[str, str]) -> dict:
    entries = []
    for document_id, text in documents.items():
        payload = text.encode("utf-8")
        entries.append(
            {
                "document_id": document_id,
                "file": f"{document_id}.md",
                "bytes": len(payload),
                "sections": text.count("\n## "),
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        )
    base_files = sorted(BASE_DIR.glob("*.md"))
    return {
        "corpus_version": "2026-11-24-track-b",
        "generated_on": GENERATED_ON,
        "generator": "scripts/build_track_b_corpus.py",
        "seed": SEED,
        "purpose": (
            "Additive synthetic corpus used only for retrieval ablations. The runtime corpus "
            "in data/knowledge_docs/ is unchanged and remains the citation source for the demo."
        ),
        "classification": "synthetic",
        "subordinate_to": "data/knowledge_docs/",
        "base_corpus_documents": len(base_files),
        "document_count": len(entries),
        "combined_document_count": len(base_files) + len(entries),
        "section_count": sum(entry["sections"] for entry in entries),
        "total_bytes": sum(entry["bytes"] for entry in entries),
        "families": {
            "area_policy_addenda": 40,
            "category_sops": 60,
            "supplier_term_addenda": 40,
            "case_notes": 120,
            "operations_circulars": 110,
            "training_quick_references": 110,
        },
        "documents": entries,
    }


def _write(documents: dict[str, str], manifest: dict) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    expected_names = {f"{document_id}.md" for document_id in documents}
    for stale in OUT_DIR.glob("*.md"):
        if stale.name not in expected_names:
            stale.unlink()
    for document_id, text in documents.items():
        (OUT_DIR / f"{document_id}.md").write_text(text, encoding="utf-8", newline="\n")
    (OUT_DIR / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
    )


def _check(documents: dict[str, str], manifest: dict) -> int:
    if not OUT_DIR.is_dir():
        print(f"missing corpus directory: {OUT_DIR}")
        return 1
    problems = 0
    files = {path.name for path in OUT_DIR.glob("*.md")}
    expected = {f"{document_id}.md" for document_id in documents}
    for missing in sorted(expected - files):
        print(f"missing: {missing}")
        problems += 1
    for extra in sorted(files - expected):
        print(f"unexpected: {extra}")
        problems += 1
    for document_id, text in documents.items():
        path = OUT_DIR / f"{document_id}.md"
        if path.exists() and path.read_text(encoding="utf-8") != text:
            print(f"out of date: {path.name}")
            problems += 1
    manifest_path = OUT_DIR / "manifest.json"
    if not manifest_path.exists():
        print("missing: manifest.json")
        problems += 1
    elif json.loads(manifest_path.read_text(encoding="utf-8")) != manifest:
        print("out of date: manifest.json")
        problems += 1
    if problems:
        return 1
    print(f"Track B corpus is current: {len(documents)} documents")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--write", action="store_true", help="write the generated corpus")
    group.add_argument("--check", action="store_true", help="verify the committed corpus is current")
    args = parser.parse_args()

    documents = build_documents()
    manifest = build_manifest(documents)
    if args.write:
        _write(documents, manifest)
        print(
            f"Wrote {len(documents)} documents / {manifest['section_count']} sections "
            f"({manifest['total_bytes'] / 1024:.1f} KiB) to {OUT_DIR}"
        )
        return 0
    return _check(documents, manifest)


if __name__ == "__main__":
    sys.exit(main())
