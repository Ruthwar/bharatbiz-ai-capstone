import re

from app.extraction.base import Extraction
from app.schemas.contracts import IntentMatch, MessageSubmission

RETAIL_SOURCES = {"retailer_message", "sales_visit"}
TIERS = {
    "combined_disruption": 1.0,
    "limited_cash": 0.99,
    "stock_discrepancy": 0.98,
    "demand_spike": 0.97,
    "supplier_delay": 0.96,
    "damaged_item": 0.95,
    "missing_item": 0.94,
    "competitor_observation": 0.93,
    "scheme_question": 0.90,
    "delivery_complaint": 0.88,
    "product_request": 0.85,
    "other": 0.50,
}
EXTRA_RULES = (
    ("damaged_item", re.compile(r"\b(?:damaged|broken|leak(?:ing|ed|s)?|torn|expired|spoil(?:ed|t)?|crushed)\b", re.I)),
    ("missing_item", re.compile(
        r"\bmissing\b|\bshort (?:by|in|of)\b|\bwas short\b|\bless (?:quantity|qty)\b|\bnot received\b|"
        r"\bdid(?: not|n't) (?:get|receive)\b", re.I
    )),
    ("product_request", re.compile(
        r"\bplease send\b|\bsend (?:us|me)\b|\b(?:need|want|require)\b|\bavailability\b|"
        r"\bsmaller packs?\b|\bpack sizes?\b|\bnew pack\b|\basking for\b", re.I
    )),
    ("delivery_complaint", re.compile(
        r"\bnot (?:yet )?delivered\b|\bstill waiting\b|\b(?:delivery|order)\b[^.?!]{0,30}\b(?:late|delayed)\b", re.I
    )),
)
PACK_SIZE = re.compile(r"\bsmaller packs?\b|\bpack sizes?\b|\bnew pack\b|\bsmall packs?\b", re.I)
DELAY_WORDS = re.compile(r"\b(?:late|delay(?:ed|s)?|postpon\w*)\b", re.I)


def refine_rule_intents(matches: list[IntentMatch], text: str) -> list[IntentMatch]:
    by_intent = {}
    for match in matches:
        if match.intent == "product_request" and (match.evidence_span or "").casefold() == "pack":
            if not re.search(r"\bpack\b", text, re.I) and not PACK_SIZE.search(text):
                continue
        by_intent.setdefault(match.intent, match)
    for intent, pattern in EXTRA_RULES:
        found = pattern.search(text)
        if found and intent not in by_intent:
            by_intent[intent] = IntentMatch(intent=intent, confidence=0.0, evidence_span=found.group(0))
    if "competitor_observation" in by_intent and "scheme_question" in by_intent:
        if not re.search(r"\bscheme\b", text, re.I):
            by_intent.pop("scheme_question")
    refined = [
        IntentMatch(
            intent=match.intent,
            confidence=TIERS.get(match.intent, match.confidence),
            evidence_span=match.evidence_span,
        )
        for match in by_intent.values()
    ]
    return sorted(refined, key=lambda match: -match.confidence)


def reconcile_sender(extraction: Extraction, message: MessageSubmission) -> None:
    sender = message.sender
    party = sender.party_type if sender else None
    if party not in {"retailer", "sales_rep"} or message.source_type not in RETAIL_SOURCES:
        return
    if any(match.intent == "combined_disruption" for match in extraction.intents):
        return
    names_supplier = any(extraction.fact(field) for field in ("supplier_id", "supplier_name")) or re.search(
        r"\bSUP-\d{3}\b|\bsupplier\b", message.text, re.I
    )
    if names_supplier:
        return
    delay = next((match for match in extraction.intents if match.intent == "supplier_delay"), None)
    if delay is None:
        return
    extraction.intents.remove(delay)
    if not any(match.intent == "delivery_complaint" for match in extraction.intents):
        span = delay.evidence_span
        if not span or span not in message.text:
            found = DELAY_WORDS.search(message.text)
            span = found.group(0) if found else None
        extraction.intents.append(
            IntentMatch(intent="delivery_complaint", confidence=TIERS["delivery_complaint"], evidence_span=span)
        )
    extraction.uncertainties.append(
        "Delay wording from a retailer or sales rep was read as a delivery complaint, not a supplier delay report."
    )
