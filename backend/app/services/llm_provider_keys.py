"""Validate that the active LLM provider has an API key (full RAG / requeue prerequisites)."""

from __future__ import annotations

from app.config import settings


def require_llm_api_key_for_full_mode() -> None:
    """Raise ``ValueError`` if ``eval_mode=full`` cannot call the configured provider.

    Default provider is **openai** (see ``Settings.llm_provider``). Anthropic remains
    available when ``LLM_PROVIDER=anthropic`` and ``CLAUDE_API_KEY`` is set.
    """
    p = (settings.llm_provider or "openai").strip().lower()
    if p == "anthropic":
        key = (settings.claude_api_key or "").strip()
        if not key:
            raise ValueError(
                "claude_api_key / CLAUDE_API_KEY is not set. Required when LLM_PROVIDER=anthropic."
            )
        return
    # Default and any unknown value → OpenAI-first
    key = (settings.openai_api_key or "").strip()
    if not key:
        raise ValueError(
            "openai_api_key / OPENAI_API_KEY is not set. Required for full RAG when "
            "LLM_PROVIDER is openai (default)."
        )
