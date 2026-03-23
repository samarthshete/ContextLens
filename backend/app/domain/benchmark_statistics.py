"""Thresholds for statistical validity of config comparisons (documented defaults)."""

from __future__ import annotations

from typing import Literal

# Minimum traced runs per config (within a bucket) — volume context; not sufficient alone for validity.
RECOMMENDED_MIN_TRACED_RUNS_FOR_VALID_COMPARISON: int = 20

# Distinct query cases represented in the comparison (effective sample) — primary gate for reliability.
RECOMMENDED_MIN_UNIQUE_QUERIES_FOR_VALID_COMPARISON: int = 10

ConfidenceTier = Literal["LOW", "MEDIUM", "HIGH"]


def confidence_tier_from_min_traced_runs(min_traced: int) -> ConfidenceTier:
    """Legacy tier from raw traced-run count only (kept for tests / callers that need volume-only tiers)."""
    if min_traced >= RECOMMENDED_MIN_TRACED_RUNS_FOR_VALID_COMPARISON:
        return "HIGH"
    if min_traced >= 5:
        return "MEDIUM"
    return "LOW"


def comparison_statistically_reliable(min_traced: int) -> bool:
    """Legacy: true when raw traced runs meet the 20+ recommendation (not sufficient if unique queries are tiny)."""
    return min_traced >= RECOMMENDED_MIN_TRACED_RUNS_FOR_VALID_COMPARISON


def confidence_tier_from_effective_sample_size(effective_sample_size: int) -> ConfidenceTier:
    """Heuristic confidence from distinct-query coverage (min unique queries across compared configs)."""
    if effective_sample_size < 8:
        return "LOW"
    if effective_sample_size < 15:
        return "MEDIUM"
    return "HIGH"


def comparison_statistically_reliable_by_effective_sample(effective_sample_size: int) -> bool:
    return effective_sample_size >= RECOMMENDED_MIN_UNIQUE_QUERIES_FOR_VALID_COMPARISON
