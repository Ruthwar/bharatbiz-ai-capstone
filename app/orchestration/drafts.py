import hashlib
import re

from app.schemas.retail import ResponseDraft

LANGUAGES = ("English", "Hinglish", "Hindi")

COMPLAINT_WHAT = {
    "damaged_item": {"English": "a damaged item", "Hinglish": "kharab saamaan", "Hindi": "खराब सामान"},
    "missing_item": {"English": "a missing item", "Hinglish": "kam ya gayab saamaan", "Hindi": "कम या गायब सामान"},
    "delivery_complaint": {
        "English": "a delivery problem",
        "Hinglish": "delivery ki samasya",
        "Hindi": "डिलीवरी में समस्या",
    },
}

TEMPLATES = {
    "complaint_ack": {
        "English": "Sorry for the trouble. We have noted your report of {what}{subject}{ref}. "
        "Our team will check it against the delivery record and contact you.",
        "Hinglish": "Pareshani ke liye maafi chahte hain. Aapki {what}{subject}{ref} ki report note kar li gayi hai. "
        "Hamari team delivery record se check karke aapse sampark karegi.",
        "Hindi": "असुविधा के लिए खेद है। आपकी {what}{subject}{ref} की शिकायत दर्ज कर ली गई है। "
        "हमारी टीम डिलीवरी रिकॉर्ड से जाँच करके आपसे संपर्क करेगी।",
    },
    "request_ack": {
        "English": "Thank you for your request{subject}. It has been noted, and our team will check "
        "availability and contact you.",
        "Hinglish": "Aapki request{subject} ke liye dhanyavaad. Ise note kar liya gaya hai; hamari team "
        "availability check karke aapse sampark karegi.",
        "Hindi": "आपके अनुरोध{subject} के लिए धन्यवाद। इसे दर्ज कर लिया गया है; हमारी टीम उपलब्धता "
        "जाँचकर आपसे संपर्क करेगी।",
    },
}

SUBJECT = {"English": " for {label}", "Hinglish": " ({label})", "Hindi": " ({label})"}
REF = {"English": " (order {order_id})", "Hinglish": " (order {order_id})", "Hindi": " (ऑर्डर {order_id})"}
RULES = (
    ("mentions_money", re.compile(r"₹|\brs\.?\b|\binr\b|\brupees?\b|रुपये", re.I)),
    ("mentions_date_or_time", re.compile(
        r"\b(?:today|tomorrow|tonight|yesterday|this week|next week|monday|tuesday|wednesday|thursday|friday|"
        r"saturday|sunday|kal|aaj|parso|hours?|days?)\b|कल|आज|परसों", re.I
    )),
    ("makes_commitment", re.compile(
        r"\bwill (?:be )?(?:deliver\w*|send|sent|replace\w*|refund\w*|credit\w*|compensate\w*|arrive|reach|"
        r"dispatch\w*|ship\w*)\b|\b(?:guarantee\w*|promise\w*|assure\w*|refund\w*|replacement|credit note|"
        r"compensation)\b|bhej (?:denge|diya jayega)|deliver ho jayega|भेज देंगे|बदल देंगे|रिफंड", re.I
    )),
    ("states_cause", re.compile(r"\bbecause\b|\bdue to\b|\bkyunki\b|\bki wajah se\b|क्योंकि|के कारण", re.I)),
    ("suggests_substitute", re.compile(r"\binstead\b|\bsubstitut\w*|\balternative\b|\bequivalent\b|\bbadle mein\b", re.I)),
    ("asks_question", re.compile(r"\?")),
)
DIGITS = re.compile(r"\d|[०-९]")


def check_draft(text: str | None, allowed_tokens: list[str] | tuple[str, ...] = ()) -> list[str]:
    if not text or not text.strip():
        return ["empty_text"]
    stripped = text
    for token in sorted((token for token in allowed_tokens if token), key=len, reverse=True):
        stripped = stripped.replace(token, " ")
    violations = [code for code, pattern in RULES if pattern.search(stripped)]
    if DIGITS.search(stripped):
        violations.append("contains_number")
    return violations


def build_draft(
    event_id: str,
    retailer_id: str,
    kind: str,
    language: str,
    category: str | None = None,
    product_label: str | None = None,
    order_id: str | None = None,
) -> ResponseDraft | None:
    lang = language if language in LANGUAGES else "English"
    subject = SUBJECT[lang].format(label=product_label) if product_label else ""
    ref = REF[lang].format(order_id=order_id) if order_id else ""
    if kind == "complaint_ack":
        text = TEMPLATES[kind][lang].format(what=COMPLAINT_WHAT[category][lang], subject=subject, ref=ref)
    else:
        text = TEMPLATES[kind][lang].format(subject=subject)
    allowed = [token for token in (product_label, order_id) if token]
    violations = check_draft(text, allowed)
    if violations:
        return None
    digest = hashlib.sha256(f"draft|{event_id}".encode("utf-8")).hexdigest()[:12]
    return ResponseDraft(
        draft_id=f"draft-{digest}",
        event_id=event_id,
        retailer_id=retailer_id,
        language=lang,
        kind=kind,
        text=text,
        allowed_tokens=allowed,
    )
