"""Benchmark statistics helpers (confidence tiers)."""

import pytest

pytestmark = pytest.mark.no_database_cleanup

from app.domain.benchmark_statistics import (
    RECOMMENDED_MIN_TRACED_RUNS_FOR_VALID_COMPARISON,
    RECOMMENDED_MIN_UNIQUE_QUERIES_FOR_VALID_COMPARISON,
    comparison_statistically_reliable,
    comparison_statistically_reliable_by_effective_sample,
    confidence_tier_from_effective_sample_size,
    confidence_tier_from_min_traced_runs,
)


def test_confidence_tiers_legacy_traced_volume():
    assert confidence_tier_from_min_traced_runs(0) == "LOW"
    assert confidence_tier_from_min_traced_runs(4) == "LOW"
    assert confidence_tier_from_min_traced_runs(5) == "MEDIUM"
    assert confidence_tier_from_min_traced_runs(19) == "MEDIUM"
    assert confidence_tier_from_min_traced_runs(20) == "HIGH"


def test_reliable_threshold_legacy_traced_volume():
    assert comparison_statistically_reliable(19) is False
    assert comparison_statistically_reliable(20) is True
    assert RECOMMENDED_MIN_TRACED_RUNS_FOR_VALID_COMPARISON == 20


def test_confidence_tiers_effective_sample_size():
    assert confidence_tier_from_effective_sample_size(0) == "LOW"
    assert confidence_tier_from_effective_sample_size(7) == "LOW"
    assert confidence_tier_from_effective_sample_size(8) == "MEDIUM"
    assert confidence_tier_from_effective_sample_size(14) == "MEDIUM"
    assert confidence_tier_from_effective_sample_size(15) == "HIGH"


def test_reliable_by_effective_sample():
    assert comparison_statistically_reliable_by_effective_sample(9) is False
    assert comparison_statistically_reliable_by_effective_sample(10) is True
    assert RECOMMENDED_MIN_UNIQUE_QUERIES_FOR_VALID_COMPARISON == 10
