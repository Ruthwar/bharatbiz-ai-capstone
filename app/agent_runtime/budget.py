"""Deterministic budgets: the cap is arithmetic, not a guess about the provider.

Token use is estimated from characters (four characters per token) because the
deterministic path has no tokenizer. The estimate is labelled as such everywhere it is
reported so nobody mistakes it for provider-billed usage.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field

TOKEN_ESTIMATE_BASIS = "characters/4 (deterministic estimate, not provider-billed)"


def estimate_tokens(text: str) -> int:
    return max(1, math.ceil(len(text) / 4))


@dataclass
class AgentBudget:
    """A hard cap per query: at most ten tool calls, twelve thousand estimated tokens, five seconds."""

    max_steps: int = 10
    max_estimated_tokens: int = 12_000
    max_seconds: float = 5.0
    steps: int = 0
    estimated_tokens: int = 0
    started: float = field(default_factory=time.monotonic)

    def stop_reason(self) -> str | None:
        if self.steps >= self.max_steps:
            return "step_cap"
        if self.estimated_tokens >= self.max_estimated_tokens:
            return "token_cap"
        if time.monotonic() - self.started >= self.max_seconds:
            return "time_cap"
        return None

    def take_step(self) -> None:
        self.steps += 1

    def charge(self, text: str) -> int:
        cost = estimate_tokens(text)
        self.estimated_tokens += cost
        return cost

    def snapshot(self) -> dict:
        return {
            "steps": self.steps,
            "max_steps": self.max_steps,
            "estimated_tokens": self.estimated_tokens,
            "max_estimated_tokens": self.max_estimated_tokens,
            "elapsed_ms": round((time.monotonic() - self.started) * 1000, 1),
            "max_seconds": self.max_seconds,
            "basis": TOKEN_ESTIMATE_BASIS,
        }
