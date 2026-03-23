"""Display / API rounding for metric floats (credibility — avoid false precision)."""

from __future__ import annotations

_DEFAULT_DECIMALS = 3


def round_metric_float(value: float | None, *, decimals: int = _DEFAULT_DECIMALS) -> float | None:
    """Round to *decimals* places; ``None`` unchanged."""
    if value is None:
        return None
    return round(float(value), decimals)
