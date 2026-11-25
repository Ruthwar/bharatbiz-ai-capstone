"""In-process token-bucket rate limiter for the HTTP API.

The limit is per client address and applies only to API routes. It protects the demo and any
pilot deployment from accidental request loops; it is not a substitute for a gateway limiter in
front of multiple workers. Configuration is read once at import and can be overridden for tests.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from threading import Lock


@dataclass
class LimitConfig:
    requests_per_minute: int = 600
    burst: int = 200


class TokenBucketLimiter:
    def __init__(self, config: LimitConfig | None = None) -> None:
        self._lock = Lock()
        self._buckets: dict[str, tuple[float, float]] = {}
        self._config = config or LimitConfig(
            requests_per_minute=int(os.getenv("BHARATBIZ_RATE_LIMIT_PER_MINUTE", "600")),
            burst=int(os.getenv("BHARATBIZ_RATE_LIMIT_BURST", "200")),
        )

    @property
    def config(self) -> LimitConfig:
        return self._config

    def configure(self, *, requests_per_minute: int, burst: int | None = None) -> None:
        with self._lock:
            self._config = LimitConfig(
                requests_per_minute=max(1, requests_per_minute),
                burst=max(1, burst if burst is not None else requests_per_minute),
            )
            self._buckets.clear()

    def check(self, key: str, *, now: float | None = None) -> tuple[bool, float]:
        """Consume one token. Returns (allowed, retry_after_seconds)."""
        now = time.monotonic() if now is None else now
        rate = self._config.requests_per_minute / 60.0
        capacity = float(self._config.burst)
        with self._lock:
            if len(self._buckets) > 4096:
                self._buckets.clear()
            tokens, last = self._buckets.get(key, (capacity, now))
            tokens = min(capacity, tokens + (now - last) * rate)
            if tokens < 1.0:
                retry = (1.0 - tokens) / rate if rate > 0 else 60.0
                self._buckets[key] = (tokens, now)
                return False, max(0.0, round(retry, 3))
            self._buckets[key] = (tokens - 1.0, now)
            return True, 0.0

    def reset(self) -> None:
        with self._lock:
            self._buckets.clear()

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "scope": "per client address, API routes only",
                "requests_per_minute": self._config.requests_per_minute,
                "burst": self._config.burst,
                "tracked_clients": len(self._buckets),
            }


rate_limiter = TokenBucketLimiter()
