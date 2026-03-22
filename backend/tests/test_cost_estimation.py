"""``cost_usd`` estimation: disabled pricing and token-null semantics."""

from decimal import Decimal

from app.services import cost_estimation as ce


def test_pricing_disabled_returns_none(monkeypatch):
    monkeypatch.setattr(ce.settings, "llm_provider", "anthropic")
    monkeypatch.setattr(ce.settings, "anthropic_input_usd_per_million_tokens", 0.0)
    monkeypatch.setattr(ce.settings, "anthropic_output_usd_per_million_tokens", 0.0)
    assert ce.estimate_usd_from_tokens(100, 200) is None
    assert ce.estimate_usd_from_tokens(None, None) is None


def test_unknown_tokens_returns_none_even_when_rates_on(monkeypatch):
    monkeypatch.setattr(ce.settings, "llm_provider", "anthropic")
    monkeypatch.setattr(ce.settings, "anthropic_input_usd_per_million_tokens", 3.0)
    monkeypatch.setattr(ce.settings, "anthropic_output_usd_per_million_tokens", 15.0)
    assert ce.estimate_usd_from_tokens(None, None) is None


def test_zero_tokens_returns_decimal_zero_when_rates_on(monkeypatch):
    monkeypatch.setattr(ce.settings, "llm_provider", "anthropic")
    monkeypatch.setattr(ce.settings, "anthropic_input_usd_per_million_tokens", 3.0)
    monkeypatch.setattr(ce.settings, "anthropic_output_usd_per_million_tokens", 15.0)
    v = ce.estimate_usd_from_tokens(0, 0)
    assert v is not None
    assert v == Decimal("0")


def test_partial_rate_uses_positive_side_only(monkeypatch):
    monkeypatch.setattr(ce.settings, "llm_provider", "anthropic")
    monkeypatch.setattr(ce.settings, "anthropic_input_usd_per_million_tokens", 3.0)
    monkeypatch.setattr(ce.settings, "anthropic_output_usd_per_million_tokens", 0.0)
    v = ce.estimate_usd_from_tokens(1_000_000, 1_000_000)
    assert v is not None
    assert v == Decimal("3")


def test_openai_pricing_disabled_returns_none(monkeypatch):
    monkeypatch.setattr(ce.settings, "llm_provider", "openai")
    monkeypatch.setattr(ce.settings, "openai_input_usd_per_million_tokens", 0.0)
    monkeypatch.setattr(ce.settings, "openai_output_usd_per_million_tokens", 0.0)
    assert ce.estimate_usd_from_tokens(100, 200) is None


def test_openai_rates_used_when_provider_openai(monkeypatch):
    monkeypatch.setattr(ce.settings, "llm_provider", "openai")
    monkeypatch.setattr(ce.settings, "openai_input_usd_per_million_tokens", 1.0)
    monkeypatch.setattr(ce.settings, "openai_output_usd_per_million_tokens", 2.0)
    monkeypatch.setattr(ce.settings, "anthropic_input_usd_per_million_tokens", 99.0)
    monkeypatch.setattr(ce.settings, "anthropic_output_usd_per_million_tokens", 99.0)
    v = ce.estimate_usd_from_tokens(1_000_000, 500_000)
    assert v is not None
    assert v == Decimal("2")
