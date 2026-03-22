"""Estimate USD from token usage using configured per-million rates.

Environment (via ``Settings`` / ``.env``):

- **Active provider** is ``Settings.llm_provider`` (``LLM_PROVIDER``, default ``openai``).
- **OpenAI:** ``OPENAI_INPUT_USD_PER_MILLION_TOKENS`` / ``OPENAI_OUTPUT_USD_PER_MILLION_TOKENS``.
- **Anthropic (fallback):** ``ANTHROPIC_INPUT_USD_PER_MILLION_TOKENS`` /
  ``ANTHROPIC_OUTPUT_USD_PER_MILLION_TOKENS``.

**Disabled pricing:** both rates ≤ 0 → always ``None`` (callers should persist
``cost_usd`` as SQL NULL, not ``0``).

**Partial rates:** if only one rate is > 0, cost uses that side only; the other
token count is ignored for billing (still 0 USD from that side).

**Unknown usage:** both ``input_tokens`` and ``output_tokens`` are ``None`` → ``None``
(even when pricing is enabled — do not invent zeros).
"""

from __future__ import annotations

from decimal import Decimal

from app.config import settings


def _pricing_rates_for_active_provider() -> tuple[float, float]:
    p = (settings.llm_provider or "openai").strip().lower()
    if p == "anthropic":
        return (
            settings.anthropic_input_usd_per_million_tokens,
            settings.anthropic_output_usd_per_million_tokens,
        )
    return (
        settings.openai_input_usd_per_million_tokens,
        settings.openai_output_usd_per_million_tokens,
    )


def estimate_usd_from_tokens(
    input_tokens: int | None,
    output_tokens: int | None,
) -> Decimal | None:
    """Return USD estimate, or ``None`` if pricing is off or token counts are unknown.

    Uses per-million rates for the **active** ``llm_provider`` (OpenAI vs Anthropic);
    does not mix Anthropic rates for OpenAI token counts.

    With pricing enabled and both counts zero, returns ``Decimal('0')`` (honest zero
    usage), not ``None``.
    """
    pin, pout = _pricing_rates_for_active_provider()
    if pin <= 0 and pout <= 0:
        return None
    if input_tokens is None and output_tokens is None:
        return None
    it = input_tokens or 0
    ot = output_tokens or 0
    usd = Decimal("0")
    if pin > 0:
        usd += Decimal(str(pin)) * Decimal(it) / Decimal(1_000_000)
    if pout > 0:
        usd += Decimal(str(pout)) * Decimal(ot) / Decimal(1_000_000)
    return usd.quantize(Decimal("0.000001"))
