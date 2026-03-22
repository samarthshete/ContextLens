"""``require_llm_api_key_for_full_mode`` — provider-aware key checks."""

import pytest

from app.config import settings
from app.services import llm_provider_keys as lk


def test_openai_default_requires_openai_key(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "llm_provider", "openai")
    monkeypatch.setattr(settings, "openai_api_key", "")
    monkeypatch.setattr(settings, "claude_api_key", "sk-ant-test")
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        lk.require_llm_api_key_for_full_mode()


def test_openai_ok_when_key_set(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "llm_provider", "openai")
    monkeypatch.setattr(settings, "openai_api_key", "sk-test")
    lk.require_llm_api_key_for_full_mode()


def test_anthropic_requires_claude_key(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "llm_provider", "anthropic")
    monkeypatch.setattr(settings, "claude_api_key", "")
    monkeypatch.setattr(settings, "openai_api_key", "sk-test")
    with pytest.raises(ValueError, match="CLAUDE_API_KEY"):
        lk.require_llm_api_key_for_full_mode()
