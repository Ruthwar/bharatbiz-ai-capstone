"""Slot specifications: what a decision needs before an item can be routed."""

from pydantic import BaseModel

from app.extraction.base import Extraction


class SlotSpec(BaseModel):
    intent: str
    required: list[str]
    optional: list[str] = []
    askable_by: list[str] = []
    max_rounds: int = 2
    questions_allowed: bool = True


SLOT_SPECS: dict[str, SlotSpec] = {
    "supplier_delay": SlotSpec(
        intent="supplier_delay",
        required=["supplier_id", "product", "delay_days"],
        optional=["delayed_quantity", "revised_date", "po_reference"],
        askable_by=["supplier"],
    ),
    "delivery_complaint": SlotSpec(
        intent="delivery_complaint",
        required=["retailer_id", "product"],
        optional=["quantity", "order_reference"],
        askable_by=["retailer"],
    ),
    "damaged_item": SlotSpec(
        intent="damaged_item",
        required=["retailer_id", "product"],
        optional=["quantity"],
        askable_by=["retailer"],
    ),
    "missing_item": SlotSpec(
        intent="missing_item",
        required=["retailer_id", "product"],
        optional=["quantity"],
        askable_by=["retailer"],
    ),
    "product_request": SlotSpec(
        intent="product_request",
        required=["retailer_id", "product"],
        optional=["quantity"],
        askable_by=["retailer"],
    ),
    "scheme_question": SlotSpec(
        intent="scheme_question",
        required=["retailer_id"],
        optional=["product"],
        askable_by=["retailer"],
    ),
    "competitor_observation": SlotSpec(
        intent="competitor_observation",
        required=[],
        optional=["product"],
        askable_by=[],
    ),
    "other": SlotSpec(intent="other", required=[], optional=[], askable_by=[], questions_allowed=False),
}

# Only these slots can change the recommended plan, so only these may be asked for.
DECISION_RELEVANT: dict[str, tuple[str, ...]] = {
    "supplier_delay": ("product", "delay_days", "supplier_id"),
    "delivery_complaint": ("product", "retailer_id"),
    "damaged_item": ("product", "retailer_id"),
    "missing_item": ("product", "retailer_id"),
    "product_request": ("product", "retailer_id"),
    "scheme_question": ("retailer_id",),
    "competitor_observation": (),
    "other": (),
}

QUESTIONS: dict[tuple[str, str], dict[str, str]] = {
    ("supplier_delay", "product"): {
        "English": "Which product and pack is affected?",
        "Hinglish": "Kaunsa product aur pack affected hai?",
        "Hindi": "कौन सा प्रोडक्ट और पैक प्रभावित है?",
    },
    ("supplier_delay", "delay_days"): {
        "English": "How many days is the delay?",
        "Hinglish": "Delay kitne din ka hai?",
        "Hindi": "डिलीवरी कितने दिन देर से है?",
    },
    ("supplier_delay", "supplier_id"): {
        "English": "Which supplier reference is this about?",
        "Hinglish": "Kaunsa supplier reference hai?",
        "Hindi": "यह किस सप्लायर संदर्भ के बारे में है?",
    },
    ("delivery_complaint", "retailer_id"): {
        "English": "Which retailer is this for?",
        "Hinglish": "Kaunsa retailer hai?",
        "Hindi": "यह किस रिटेलर के लिए है?",
    },
    ("delivery_complaint", "product"): {
        "English": "Which product and pack?",
        "Hinglish": "Kaunsa product aur pack?",
        "Hindi": "कौन सा प्रोडक्ट और पैक?",
    },
    ("damaged_item", "product"): {
        "English": "Which product and pack was damaged?",
        "Hinglish": "Kaunsa product aur pack damaged tha?",
        "Hindi": "कौन सा प्रोडक्ट और पैक खराब था?",
    },
    ("damaged_item", "retailer_id"): {
        "English": "Which retailer is this for?",
        "Hinglish": "Kaunsa retailer hai?",
        "Hindi": "यह किस रिटेलर के लिए है?",
    },
    ("missing_item", "product"): {
        "English": "Which product and pack was missing?",
        "Hinglish": "Kaunsa product aur pack missing tha?",
        "Hindi": "कौन सा प्रोडक्ट और पैक गायब था?",
    },
    ("missing_item", "retailer_id"): {
        "English": "Which retailer is this for?",
        "Hinglish": "Kaunsa retailer hai?",
        "Hindi": "यह किस रिटेलर के लिए है?",
    },
    ("product_request", "product"): {
        "English": "Which product and pack do you need?",
        "Hinglish": "Kaunsa product aur pack chahiye?",
        "Hindi": "कौन सा प्रोडक्ट और पैक चाहिए?",
    },
    ("product_request", "retailer_id"): {
        "English": "Which retailer is this for?",
        "Hinglish": "Kaunsa retailer hai?",
        "Hindi": "यह किस रिटेलर के लिए है?",
    },
    ("scheme_question", "retailer_id"): {
        "English": "Which retailer is asking?",
        "Hinglish": "Kaunsa retailer pooch raha hai?",
        "Hindi": "कौन सा रिटेलर पूछ रहा है?",
    },
}


def _has_slot(extraction: Extraction, slot: str) -> bool:
    if slot == "product":
        return bool(extraction.inferences.get("catalogue_sku_id"))
    if slot == "quantity":
        return extraction.fact("quantity") is not None or extraction.fact("delayed_quantity") is not None
    return extraction.fact(slot) is not None


def missing_slots(intent: str, extraction: Extraction) -> list[str]:
    spec = SLOT_SPECS.get(intent)
    if not spec:
        return []
    return [slot for slot in spec.required if not _has_slot(extraction, slot)]


def next_question(intent: str, extraction: Extraction, party_type: str, language: str) -> str | None:
    """One template question for the highest-priority missing slot, or None."""
    spec = SLOT_SPECS.get(intent)
    if not spec or not spec.questions_allowed:
        return None
    if party_type not in spec.askable_by:
        return None
    language = language if language in {"English", "Hindi", "Hinglish"} else "English"
    for slot in missing_slots(intent, extraction):
        if slot not in DECISION_RELEVANT.get(intent, ()):
            continue
        template = QUESTIONS.get((intent, slot))
        if template:
            return template.get(language) or template["English"]
    return None
