"""Prompt-injection signals for free-form channel text.

Detection never changes routing or approval: a valid business message that also contains an
embedded instruction still produces the same pending-review plan. The signals are recorded so
an operator can see that the text tried to redirect the assistant, and the LLM extraction prompt
states that message content is data, never instructions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_SIGNALS: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        "instruction_override",
        re.compile(
            r"\b(ignore|disregard|forget|override)\b[^.\n]{0,40}\b(previous|prior|above|earlier|system)\b"
            r"[^.\n]{0,20}\b(instructions?|prompts?|rules?)\b",
            re.IGNORECASE,
        ),
        "Text asks the assistant to ignore its instructions.",
    ),
    (
        "role_spoof",
        re.compile(r"(?:^|[.\n])\s*(system|assistant|developer)\s*:", re.IGNORECASE),
        "Text contains a forged system or assistant role marker.",
    ),
    (
        "review_bypass",
        re.compile(
            r"\b(bypass|skip|approve automatically|auto[- ]?approve|without (human|manual) (review|approval))\b",
            re.IGNORECASE,
        ),
        "Text asks to bypass human review.",
    ),
    (
        "autonomous_action",
        re.compile(
            r"\b(place|confirm|execute|process|release|approve)\b[^.\n]{0,30}"
            r"\b(order|payment|purchase|dispatch|stock|transfer)\b"
            r"|\b(pay|transfer)\b[^.\n]{0,20}\b(now|immediately|automatically)\b",
            re.IGNORECASE,
        ),
        "Text asks for an action the system must never take autonomously.",
    ),
    (
        "secret_exfiltration",
        re.compile(
            r"\b(reveal|print|show|share|send|export|list)\b[^.\n]{0,40}"
            r"\b(system prompt|api key|token|password|secret|credential|phone list|customer list|contact list)\b",
            re.IGNORECASE,
        ),
        "Text asks to reveal instructions, credentials or personal data.",
    ),
)


@dataclass
class InjectionSignal:
    kind: str
    detail: str


@dataclass
class InjectionScan:
    signals: list[InjectionSignal] = field(default_factory=list)

    @property
    def flagged(self) -> bool:
        return bool(self.signals)

    def summary(self) -> dict:
        return {
            "flagged": self.flagged,
            "kinds": sorted({signal.kind for signal in self.signals}),
            "details": [signal.detail for signal in self.signals],
        }


def scan(text: str) -> InjectionScan:
    signals: list[InjectionSignal] = []
    seen: set[str] = set()
    for kind, pattern, detail in _SIGNALS:
        if kind in seen:
            continue
        if pattern.search(text):
            seen.add(kind)
            signals.append(InjectionSignal(kind=kind, detail=detail))
    return InjectionScan(signals=signals)
