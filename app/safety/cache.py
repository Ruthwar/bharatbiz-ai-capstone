"""Bounded in-process cache for read-only API responses.

Only explicitly allow-listed GET paths are cached. Any non-GET request clears the cache so a
scenario run, review decision or reset can never be observed through a stale read. Nothing is
persisted and response bodies never leave the process.
"""

from __future__ import annotations

import os
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from threading import Lock


@dataclass
class CacheStats:
    hits: int = 0
    misses: int = 0
    stores: int = 0
    evictions: int = 0
    clears: int = 0
    entries: int = 0


@dataclass
class CachedResponse:
    body: bytes
    status_code: int
    media_type: str | None
    headers: dict[str, str] = field(default_factory=dict)


class TTLCache:
    def __init__(self, *, max_entries: int = 128, ttl_seconds: float = 5.0) -> None:
        self.max_entries = max(1, max_entries)
        self.ttl_seconds = max(0.0, ttl_seconds)
        self._entries: OrderedDict[str, tuple[float, CachedResponse]] = OrderedDict()
        self._lock = Lock()
        self._stats = CacheStats()

    @property
    def enabled(self) -> bool:
        return self.ttl_seconds > 0

    def get(self, key: str) -> CachedResponse | None:
        if not self.enabled:
            return None
        now = time.monotonic()
        with self._lock:
            item = self._entries.get(key)
            if item is None:
                self._stats.misses += 1
                return None
            stored_at, response = item
            if now - stored_at > self.ttl_seconds:
                self._entries.pop(key, None)
                self._stats.misses += 1
                return None
            self._entries.move_to_end(key)
            self._stats.hits += 1
            return response

    def set(self, key: str, response: CachedResponse) -> None:
        if not self.enabled:
            return
        with self._lock:
            self._entries[key] = (time.monotonic(), response)
            self._entries.move_to_end(key)
            self._stats.stores += 1
            while len(self._entries) > self.max_entries:
                self._entries.popitem(last=False)
                self._stats.evictions += 1

    def clear(self) -> None:
        with self._lock:
            if self._entries:
                self._stats.clears += 1
            self._entries.clear()

    def stats(self) -> dict:
        with self._lock:
            data = CacheStats(**vars(self._stats))
            data.entries = len(self._entries)
        total = data.hits + data.misses
        return {
            "enabled": self.enabled,
            "ttl_seconds": self.ttl_seconds,
            "max_entries": self.max_entries,
            "entries": data.entries,
            "hits": data.hits,
            "misses": data.misses,
            "stores": data.stores,
            "evictions": data.evictions,
            "clears": data.clears,
            "hit_rate": round(data.hits / total, 4) if total else 0.0,
        }

    def reset(self) -> None:
        with self._lock:
            self._entries.clear()
            self._stats = CacheStats()


response_cache = TTLCache(
    max_entries=int(os.getenv("BHARATBIZ_CACHE_MAX_ENTRIES", "128")),
    ttl_seconds=float(os.getenv("BHARATBIZ_CACHE_TTL_SECONDS", "5")),
)
