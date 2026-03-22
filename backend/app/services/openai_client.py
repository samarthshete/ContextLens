"""Lazy AsyncOpenAI client (requires ``openai_api_key``)."""

from __future__ import annotations

from functools import lru_cache

from openai import AsyncOpenAI

from app.config import settings


def require_openai_api_key() -> str:
    key = (settings.openai_api_key or "").strip()
    if not key:
        raise ValueError(
            "openai_api_key / OPENAI_API_KEY is not set. Required when LLM_PROVIDER=openai (default)."
        )
    return key


@lru_cache(maxsize=1)
def _client(api_key: str) -> AsyncOpenAI:
    return AsyncOpenAI(api_key=api_key)


def get_async_openai() -> AsyncOpenAI:
    return _client(require_openai_api_key())
