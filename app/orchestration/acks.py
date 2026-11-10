"""Template acknowledgements. Never model-generated, never assertive."""

ACK_KINDS = ("receipt", "complete")

ACK_TEXTS: dict[str, dict[str, str]] = {
    "receipt": {
        "English": "Received. It will be reviewed.",
        "Hinglish": "Mil gaya. Review kiya jayega.",
        "Hindi": "प्राप्त हुआ। इसकी समीक्षा की जाएगी।",
    },
    "complete": {
        "English": "All details noted. It will be processed.",
        "Hinglish": "Sab details note kar li. Process kiya jayega.",
        "Hindi": "सभी विवरण दर्ज कर लिए गए। इसे प्रोसेस किया जाएगा।",
    },
}


def language_key(language: str) -> str:
    return language if language in {"English", "Hindi", "Hinglish"} else "English"


def ack_text(kind: str, language: str) -> str:
    if kind not in ACK_TEXTS:
        raise ValueError(f"Unknown acknowledgement kind: {kind}")
    texts = ACK_TEXTS[kind]
    return texts[language_key(language)]
