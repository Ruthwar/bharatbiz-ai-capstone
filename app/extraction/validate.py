"""Pre-plan gates for extraction output. The model proposes; deterministic code decides."""

import re

from app.extraction.base import Extraction
from app.extraction.rules import DAY_WORDS, find_named_row, match_catalogue_name, resolve_product
from app.schemas.contracts import BusinessState, EvidenceFact, MessageSubmission

SUPPLIER_PATTERN = re.compile(r"^SUP-\d{3}$")
RETAILER_PATTERN = re.compile(r"^RET-\d{3}$")
DAY_TOKEN_PATTERN = re.compile(r"\b(\d{1,3}|" + "|".join(DAY_WORDS) + r")\b", re.I)


def _normalise_day_count(fact) -> None:
    """Keep the evidence verbatim; store the day count as digits for deterministic arithmetic."""
    if fact.value.strip().isdigit():
        return
    for source in (fact.value, fact.evidence_span):
        match = DAY_TOKEN_PATTERN.search(source or "")
        if match:
            token = match.group(1).lower()
            fact.value = token if token.isdigit() else str(DAY_WORDS[token])
            return


def normalise_spans(extraction: Extraction, text: str) -> None:
    """Keep only facts whose evidence is an exact substring; the server computes offsets itself."""
    kept = []
    seen: set[str] = set()
    for fact in extraction.facts:
        if not fact.value.strip() or not fact.evidence_span:
            extraction.uncertainties.append(f"Dropped {fact.field}: empty value or evidence.")
            continue
        if fact.span_start is not None and fact.span_end is not None:
            if text[fact.span_start:fact.span_end] == fact.evidence_span:
                if fact.field not in seen:
                    seen.add(fact.field)
                    kept.append(fact)
                continue
        start = text.find(fact.evidence_span)
        if start < 0:
            extraction.uncertainties.append(
                f"Dropped {fact.field}: evidence span not found verbatim in the source."
            )
            continue
        if fact.field in seen:
            extraction.uncertainties.append(f"Dropped duplicate {fact.field}.")
            continue
        fact.span_start = start
        fact.span_end = start + len(fact.evidence_span)
        seen.add(fact.field)
        kept.append(fact)
    extraction.facts = kept

    for intent in extraction.intents:
        intent.confidence = min(max(intent.confidence, 0.0), 1.0)
        if intent.evidence_span and intent.evidence_span not in text:
            extraction.uncertainties.append(
                f"Dropped evidence for {intent.intent}: span not found verbatim in the source."
            )
            intent.evidence_span = None


def apply_catalogue_authority(extraction: Extraction, state: BusinessState) -> list[str]:
    """A model may propose a label; only the catalogue may assign a SKU."""
    violations = []
    sku_ids = {product["sku_id"] for product in state.products}
    proposed = extraction.inferences.get("catalogue_sku_id")
    if proposed and proposed not in sku_ids:
        extraction.inferences.pop("catalogue_sku_id", None)
        violations.append(f"sku_not_in_catalogue:{proposed}")

    if not extraction.inferences.get("catalogue_sku_id"):
        product_fact = extraction.fact("product")
        if product_fact:
            resolved = resolve_product(state, product_fact.evidence_span)
            if resolved:
                extraction.inferences["catalogue_sku_id"] = resolved["sku_id"]
            else:
                extraction.uncertainties.append(
                    "Product could not be resolved to a single catalogue SKU; clarification required."
                )
    return violations


def resolve_business_references(extraction: Extraction, text: str, state: BusinessState) -> list[str]:
    """People write trade names; plans key on catalogue IDs. Only the catalogue may assign an ID."""
    violations = []
    references = (
        ("supplier", "supplier_id", "supplier_name", state.suppliers, SUPPLIER_PATTERN),
        ("retailer", "retailer_id", "retailer_name", state.retailers, RETAILER_PATTERN),
    )
    for label, id_field, name_field, rows, pattern in references:
        named = extraction.fact(name_field)
        if named is not None:
            extraction.facts.remove(named)
            if extraction.fact(id_field) is None:
                resolved = match_catalogue_name(named.value, named.evidence_span, rows, id_field, name_field)
                if resolved:
                    named.field = id_field
                    named.value = resolved
                    extraction.facts.append(named)
                else:
                    extraction.uncertainties.append(
                        f"{label.capitalize()} name did not match a single catalogue record; clarification required."
                    )

        reference = extraction.fact(id_field)
        if reference is not None and not pattern.match(reference.value):
            resolved = match_catalogue_name(reference.value, reference.evidence_span, rows, id_field, name_field)
            if resolved:
                reference.value = resolved
            else:
                unresolved = reference.value
                extraction.facts.remove(reference)
                violations.append(f"{label}_not_in_catalogue:{unresolved}")

        if extraction.fact(id_field) is None:
            found = find_named_row(text, rows, name_field)
            if found:
                row, start, end = found
                extraction.facts.append(
                    EvidenceFact(
                        field=id_field,
                        value=row[id_field],
                        evidence_span=text[start:end],
                        span_start=start,
                        span_end=end,
                    )
                )
    return violations


def validate_extraction(
    extraction: Extraction, message: MessageSubmission, state: BusinessState
) -> list[str]:
    violations = []
    normalise_spans(extraction, message.text)
    violations.extend(apply_catalogue_authority(extraction, state))
    violations.extend(resolve_business_references(extraction, message.text, state))

    for fact in extraction.facts:
        if fact.field == "delay_days":
            _normalise_day_count(fact)
            try:
                if int(fact.value) <= 0:
                    violations.append("delay_days_not_positive")
            except ValueError:
                violations.append(f"delay_days_not_integer:{fact.value}")
        if fact.field == "supplier_id" and not SUPPLIER_PATTERN.match(fact.value):
            violations.append(f"supplier_id_not_catalogue_format:{fact.value}")

    if not extraction.intents:
        violations.append("no_intent_classified")
    return violations
