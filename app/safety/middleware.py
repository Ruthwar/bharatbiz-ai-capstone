"""ASGI middleware for the read-only response cache and per-client rate limiting."""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.safety.cache import CachedResponse, response_cache
from app.safety.limiter import rate_limiter

CACHEABLE_PREFIXES: tuple[str, ...] = (
    "/api/v1/status",
    "/api/v1/parties",
    "/api/v1/scenarios",
    "/api/v1/agent/tools",
    "/api/v1/retail/fulfilment",
)
_RATE_LIMIT_EXEMPT = ("/health",)


def _cacheable(request: Request) -> bool:
    if request.method != "GET":
        return False
    path = request.url.path
    return any(path == prefix or path.startswith(prefix + "/") for prefix in CACHEABLE_PREFIXES)


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if not path.startswith("/api/") or path in _RATE_LIMIT_EXEMPT:
            return await call_next(request)
        key = request.client.host if request.client else "unknown"
        allowed, retry_after = rate_limiter.check(key)
        if not allowed:
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "rate_limited",
                    "message": "Too many requests; retry later.",
                    "retry_after_seconds": retry_after,
                },
                headers={"Retry-After": str(max(1, int(round(retry_after))))},
            )
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(rate_limiter.config.requests_per_minute)
        return response


class ReadCacheMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method not in {"GET", "HEAD"}:
            response_cache.clear()
            return await call_next(request)
        if not _cacheable(request):
            return await call_next(request)

        key = request.url.path + ("?" + request.url.query if request.url.query else "")
        cached = response_cache.get(key)
        if cached is not None:
            headers = {**cached.headers, "X-Cache": "hit"}
            return Response(
                content=cached.body,
                status_code=cached.status_code,
                media_type=cached.media_type,
                headers=headers,
            )

        response = await call_next(request)
        if response.status_code != 200 or "application/json" not in response.headers.get(
            "content-type", ""
        ):
            response.headers["X-Cache"] = "bypass"
            return response

        body = b"".join([chunk async for chunk in response.body_iterator])
        headers = {
            key: value
            for key, value in response.headers.items()
            if key.lower() not in {"content-length", "transfer-encoding"}
        }
        response_cache.set(
            key,
            CachedResponse(
                body=body,
                status_code=response.status_code,
                media_type=response.media_type,
                headers=headers,
            ),
        )
        headers["X-Cache"] = "miss"
        return Response(
            content=body,
            status_code=response.status_code,
            media_type=response.media_type,
            headers=headers,
        )
