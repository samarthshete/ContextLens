"""Benchmark statistics helpers (confidence tiers)."""

from app.domain.benchmark_statistics import (
    RECOMMENDED_MIN_TRACED_RUNS_FOR_VALID_COMPARISON,
    comparison_statistically_reliable,
    confidence_tier_from_min_traced_runs,
)


def test_confidence_tiers():
    assert confidence_tier_from_min_traced_runs(0) == "LOW"
    assert confidence_tier_from_min_traced_runs(4) == "LOW"
    assert confidence_tier_from_min_traced_runs(5) == "MEDIUM"
    assert confidence_tier_from_min_traced_runs(19) == "MEDIUM"
    assert confidence_tier_from_min_traced_runs(20) == "HIGH"


def test_reliable_threshold():
    assert comparison_statistically_reliable(19) is False
    assert comparison_statistically_reliable(20) is True
    assert RECOMMENDED_MIN_TRACED_RUNS_FOR_VALID_COMPARISON == 20
