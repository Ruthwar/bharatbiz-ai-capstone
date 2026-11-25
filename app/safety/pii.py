"""Detect and mask Indian personal identifiers before text leaves the process.

The default LLM path is rules-only. When a model is enabled, message text is masked before the
request is built. Masking preserves the length of the original text so downstream evidence
offsets stay comparable; a quote that contained a masked identifier will fail the exact-span
gate and the extraction falls back to rules, which is the intended fail-safe.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

# Ordered most-specific first so a GSTIN is not half-consumed as a phone or PAN.
_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("gstin", re.compile(r"\b\d{2}[A-Z]{5}\d{4}[A-Z]\d[Z][A-Z\d]\b")),
    ("pan", re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b")),
    ("email", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")),
    ("upi", re.compile(r"\b[\w.-]{2,}@(?:okhdfcbank|okicici|oksbi|okaxis|ybl|paytm|upi)\b", re.IGNORECASE)),
    ("aadhaar", re.compile(r"\b\d{4}\s?\d{4}\s?\d{4}\b")),
    ("phone", re.compile(r"(?<!\d)(?:\+91[-\s]?)?[6-9]\d{4}[\s-]?\d{5}(?!\d)")),
    ("card", re.compile(r"\b(?:\d[ -]?){15}\d\b")),
)

PII_TYPES = tuple(name for name, _ in _PATTERNS)
_MASK_CHAR = {"phone": "#", "aadhaar": "#", "card": "#", "gstin": "*", "pan": "*", "email": "*", "upi": "*"}


@dataclass
class PiiFinding:
    kind: str
    start: int
    end: int


@dataclass
class PiiScan:
    findings: list[PiiFinding] = field(default_factory=list)

    @property
    def detected(self) -> bool:
        return bool(self.findings)

    def counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for finding in self.findings:
            counts[finding.kind] = counts.get(finding.kind, 0) + 1
        return counts

    def summary(self) -> dict:
        return {"detected": self.detected, "counts": self.counts(), "total": len(self.findings)}


def scan(text: str) -> PiiScan:
    findings: list[PiiFinding] = []
    claimed: list[tuple[int, int]] = []
    for kind, pattern in _PATTERNS:
        for match in pattern.finditer(text):
            start, end = match.span()
            if any(start < other_end and other_start < end for other_start, other_end in claimed):
                continue
            claimed.append((start, end))
            findings.append(PiiFinding(kind=kind, start=start, end=end))
    findings.sort(key=lambda item: item.start)
    return PiiScan(findings=findings)


def mask(text: str) -> tuple[str, PiiScan]:
    """Return text with identifiers masked in place, keeping the original length."""
    result = scan(text)
    if not result.findings:
        return text, result
    chars = list(text)
    for finding in result.findings:
        marker = _MASK_CHAR.get(finding.kind, "#")
        for index in range(finding.start, finding.end):
            char = chars[index]
            if char.isalnum():
                chars[index] = marker
    return "".join(chars), result


def redaction_enabled() -> bool:
    return os.getenv("BHARATBIZ_PII_REDACTION", "mask").strip().lower() != "off"


def prepare_for_model(text: str) -> tuple[str, dict]:
    """Mask identifiers before an external model call when redaction is enabled."""
    if not redaction_enabled():
        return text, {"redaction": "off", **scan(text).summary()}
    masked, result = mask(text)
    return masked, {"redaction": "masked", **result.summary()}
