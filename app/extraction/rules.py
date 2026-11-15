"""Deterministic extractor. Wraps the original regex logic unchanged behind the extraction interface."""

import re

from app.extraction.base import Extraction
from app.extraction.retail_intents import RETAIL_SOURCES, refine_rule_intents
from app.schemas.contracts import BusinessState, EvidenceFact, IntentMatch, MessageSubmission

RULES = (
    ("combined_disruption", re.compile(r"combined\s+disruption", re.I)),
    ("limited_cash", re.compile(r"limited\s+cash|cash\s+(?:constraint|shortage)|payment\s+(?:is\s+)?delayed", re.I)),
    ("stock_discrepancy", re.compile(r"stock\s+discrepancy|physical\s+count|stock\s+mismatch", re.I)),
    ("demand_spike", re.compile(r"demand\s+(?:spike|surge)|demand\s+up|orders?.+rise\s+by", re.I)),
    ("baseline", re.compile(r"baseline\s+day", re.I)),
    ("supplier_delay", re.compile(r"delay|late|postpon", re.I)),
    ("damaged_item", re.compile(r"damaged|broken|leaking", re.I)),
    ("missing_item", re.compile(r"missing\s+(?:item|pack|quantity)|short\s+shipped", re.I)),
    ("delivery_complaint", re.compile(r"delivery|delivered|arriv", re.I)),
    ("product_request", re.compile(r"request|need|asking|pack", re.I)),
    ("competitor_observation", re.compile(r"competitor|nearby shop", re.I)),
    ("scheme_question", re.compile(r"scheme|offer|discount", re.I)),
)
DELAY_PATTERN = re.compile(
    r"\b(\d+|one|two|three|four|five|six|seven|eight|nine|ten)[-\s]days?\s+delay\b",
    re.I,
)
DAY_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}


def _fact(field: str, value: str, text: str, start: int, end: int) -> EvidenceFact:
    return EvidenceFact(
        field=field,
        value=value,
        evidence_span=text[start:end],
        span_start=start,
        span_end=end,
    )


def normalise_label(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", value.casefold()).split())


def match_catalogue_name(value: str, evidence: str, rows: list[dict], id_field: str, name_field: str) -> str | None:
    """Map a written trade name to one catalogue ID. Ambiguity returns None, never a guess."""
    catalogue = [
        (normalise_label(row.get(name_field, "")), row[id_field])
        for row in rows
        if row.get(name_field)
    ]
    for candidate in (value, evidence):
        target = normalise_label(candidate or "")
        if not target:
            continue
        exact = [identifier for name, identifier in catalogue if name == target]
        if len(exact) == 1:
            return exact[0]
        contained = [
            identifier
            for name, identifier in catalogue
            if len(name) >= 6 and (name in target or target in name)
        ]
        if len(contained) == 1:
            return contained[0]
    return None


def find_named_row(text: str, rows: list[dict], name_field: str) -> tuple[dict, int, int] | None:
    """Longest literal trade-name mention wins, so 'New Sai Kirana' beats a shared suffix."""
    best: tuple[dict, int, int] | None = None
    for row in rows:
        name = row.get(name_field, "")
        if not name:
            continue
        pattern = re.compile(r"\s+".join(re.escape(part) for part in name.split()), re.I)
        match = pattern.search(text)
        if match and (best is None or len(match.group(0)) > best[2] - best[1]):
            best = (row, match.start(), match.end())
    return best


def resolve_product(state: BusinessState, text: str) -> dict | None:
    """Resolve a product label against the catalogue. Ambiguity returns None, never a guess."""
    full_matches = []
    category_matches = []
    for product in state.products:
        full_label = f"{product['product_name']} {product['pack_description']}"
        full_match = re.search(re.escape(full_label), text, re.I)
        if full_match:
            full_matches.append((product, full_label, full_match))
        category_match = re.search(rf"\b{re.escape(product['product_name'])}\b", text, re.I)
        if category_match:
            category_matches.append((product, product["product_name"], category_match))

    matches = full_matches or category_matches
    sku_ids = {product["sku_id"] for product, _, _ in matches}
    if len(sku_ids) != 1:
        return None
    product, label, match = matches[0]
    return {
        "sku_id": product["sku_id"],
        "unit": product["base_unit"],
        "label": label,
        "start": match.start(),
        "end": match.end(),
        "match_type": "product_and_pack" if full_matches else "product_name",
    }


def classify(text: str) -> list[IntentMatch]:
    matches = []
    for name, pattern in RULES:
        match = pattern.search(text)
        if match:
            matches.append(IntentMatch(intent=name, confidence=0.9, evidence_span=match.group(0)))
    return matches


class RulesExtractor:
    name = "rules"

    def extract(self, message: MessageSubmission, state: BusinessState) -> Extraction:
        text = message.text
        facts: list[EvidenceFact] = []
        inferences: dict[str, str | bool | None] = {}

        supplier_match = re.search(r"\b(SUP-\d{3})\b", text, re.I)
        if supplier_match:
            facts.append(_fact("supplier_id", supplier_match.group(1).upper(), text, *supplier_match.span(1)))
        else:
            named_supplier = find_named_row(text, state.suppliers, "supplier_name")
            if named_supplier:
                row, start, end = named_supplier
                facts.append(_fact("supplier_id", row["supplier_id"], text, start, end))

        retailer_match = re.search(r"\b(RET-\d{3})\b", text, re.I)
        if retailer_match:
            facts.append(_fact("retailer_id", retailer_match.group(1).upper(), text, *retailer_match.span(1)))
        else:
            named_retailer = find_named_row(text, state.retailers, "retailer_name")
            if named_retailer:
                row, start, end = named_retailer
                facts.append(_fact("retailer_id", row["retailer_id"], text, start, end))

        delay_match = DELAY_PATTERN.search(text)
        if delay_match:
            raw_delay = delay_match.group(1).lower()
            delay_days = int(raw_delay) if raw_delay.isdigit() else DAY_WORDS[raw_delay]
            delay_span = text[delay_match.start():delay_match.end()].split()[0]
            facts.append(
                _fact("delay_days", str(delay_days), text, delay_match.start(), delay_match.start() + len(delay_span))
            )

        uplift_match = re.search(r"\b(?:rise\s+by|up|increase(?:d)?\s+by)\s+(\d+(?:\.\d+)?)\s*(?:percent|%)", text, re.I)
        if uplift_match:
            facts.append(_fact("demand_uplift_percent", uplift_match.group(1), text, *uplift_match.span(1)))

        count_match = re.search(r"\bphysical\s+count\s+(?:is|of|:)?\s*(\d+)\b", text, re.I)
        if count_match:
            facts.append(_fact("physical_count_units", count_match.group(1), text, *count_match.span(1)))

        order_match = re.search(r"\b(ORD-\d{4})\b", text, re.I)
        if order_match:
            facts.append(_fact("order_reference", order_match.group(1).upper(), text, *order_match.span(1)))

        product = resolve_product(state, text)
        if product:
            facts.append(_fact("product", product["label"], text, product["start"], product["end"]))
            inferences["catalogue_sku_id"] = product["sku_id"]

        intents = classify(text)
        if message.source_type in RETAIL_SOURCES:
            intents = refine_rule_intents(intents, text)
        return Extraction(
            intents=intents,
            facts=facts,
            inferences=inferences,
            mode="rules_mock",
        )
