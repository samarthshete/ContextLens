"""Lazy AsyncAnthropic client (requires ``claude_api_key``)."""

from __future__ import annotations

from functools import lru_cache

from anthropic import AsyncAnthropic

from app.config import settings


def require_api_key() -> str:
    key = (settings.claude_api_key or "").strip()
    if not key:
        raise ValueError(
            "claude_api_key / CLAUDE_API_KEY is not set. Required when using the Anthropic client."
        )
    return key


@lru_cache(maxsize=1)
def _client(api_key: str) -> AsyncAnthropic:
    return AsyncAnthropic(api_key=api_key)


def get_async_anthropic() -> AsyncAnthropic:
    return _client(require_api_key())
