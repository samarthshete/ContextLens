"""Optional write protection for hosted / production-like deployments.

When ``CONTEXTLENS_WRITE_KEY`` is non-empty, all non-safe methods on ``/api/v1/*``
require header ``X-ContextLens-Write-Key`` matching the configured value (constant-time
compare). GET/HEAD/OPTIONS are allowed without the key so the UI can stay read-only
for anonymous viewers.

This is a **demo / single-tenant** gate, not user auth: anyone who knows the key
can perform writes. For stronger isolation, use a reverse proxy or private network.
"""

from __future__ import annotations

import hmac
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.config import settings


def _configured_write_key() -> str:
    return (settings.contextlens_write_key or "").strip()


def _constant_time_key_match(expected: str, given: str) -> bool:
    if len(given) != len(expected):
        return False
    return hmac.compare_digest(given.encode("utf-8"), expected.encode("utf-8"))


class WriteProtectionMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        key = _configured_write_key()
        if not key:
            return await call_next(request)

        path = request.url.path
        if not path.startswith("/api/v1"):
            return await call_next(request)

        method = request.method.upper()
        if method in ("GET", "HEAD", "OPTIONS"):
            return await call_next(request)

        header = request.headers.get("X-ContextLens-Write-Key") or ""
        if not _constant_time_key_match(key, header):
            return JSONResponse(
                status_code=403,
                content={"detail": "write_key_required"},
            )
        return await call_next(request)
