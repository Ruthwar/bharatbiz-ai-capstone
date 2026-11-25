"""Production and safety controls for the capstone app.

Caching and rate limiting are bounded, in-process and easy to switch off; PII masking and
injection scanning are pure functions with no persistence of raw identifiers.
"""

from app.safety.cache import CachedResponse, TTLCache, response_cache
from app.safety.injection import InjectionScan, scan as scan_injection
from app.safety.limiter import LimitConfig, TokenBucketLimiter, rate_limiter
from app.safety.pii import PiiScan, mask, prepare_for_model, redaction_enabled, scan as scan_pii

__all__ = [
    "CachedResponse",
    "InjectionScan",
    "LimitConfig",
    "PiiScan",
    "TTLCache",
    "TokenBucketLimiter",
    "mask",
    "prepare_for_model",
    "rate_limiter",
    "redaction_enabled",
    "response_cache",
    "scan_injection",
    "scan_pii",
]
