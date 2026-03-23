"""Thresholds for statistical validity of config comparisons (documented defaults)."""

from __future__ import annotations

from typing import Literal

# Minimum traced runs per config (within a bucket) for "high confidence" / validity messaging.
RECOMMENDED_MIN_TRACED_RUNS_FOR_VALID_COMPARISON: int = 20

ConfidenceTier = Literal["LOW", "MEDIUM", "HIGH"]


def confidence_tier_from_min_traced_runs(min_traced: int) -> ConfidenceTier:
    if min_traced >= RECOMMENDED_MIN_TRACED_RUNS_FOR_VALID_COMPARISON:
        return "HIGH"
    if min_traced >= 5:
        return "MEDIUM"
    return "LOW"


def comparison_statistically_reliable(min_traced: int) -> bool:
    return min_traced >= RECOMMENDED_MIN_TRACED_RUNS_FOR_VALID_COMPARISON
