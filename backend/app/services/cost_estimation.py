"""Estimate USD from token usage using configured per-million rates."""

from __future__ import annotations

from decimal import Decimal

from app.config import settings


def estimate_usd_from_tokens(
    input_tokens: int | None,
    output_tokens: int | None,
) -> Decimal | None:
    """Return ``None`` if pricing is disabled (both rates <= 0) or tokens unknown."""
    pin = settings.anthropic_input_usd_per_million_tokens
    pout = settings.anthropic_output_usd_per_million_tokens
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
