"""Controlled variability + failure injection for **batch** benchmarking (opt-in).

Production / default ``POST /runs`` paths do **not** import this module. Use only from
``batch_runner`` when building realistic metric distributions for experiments.
"""

from __future__ import annotations

import copy
import random
from dataclasses import dataclass, field

from app.domain.failure_taxonomy import FailureType
from app.services.minimal_retrieval_evaluation import (
    COMPLETENESS_INCOMPLETE_THRESHOLD,
    CONTEXT_INSUFFICIENT_THRESHOLD,
    RELEVANCE_PARTIAL_THRESHOLD,
)


@dataclass
class BenchmarkRealismProfile:
    """Tuning knobs for heuristic-batch realism. All probabilities in ``[0, 1]``."""

    # Retrieval
    drop_top_chunk_probability: float = 0.2
    shuffle_lower_ranks: bool = True
    p_retrieval_empty: float = 0.0  # force empty hit list (RETRIEVAL_MISS path)

    # Scores (heuristic eval, post-compute)
    score_noise_max_delta: float = 0.05  # uniform ± this, clamped to [0, 1]

    # Low-quality classification overrides (after noise) — align with ``minimal_retrieval_evaluation``.
    relevance_low_threshold: float = RELEVANCE_PARTIAL_THRESHOLD
    context_coverage_low_threshold: float = CONTEXT_INSUFFICIENT_THRESHOLD
    completeness_low_threshold: float = COMPLETENESS_INCOMPLETE_THRESHOLD

    # Generation / LLM path: not simulated here (real provider outputs).
    extra_metadata: dict[str, object] = field(default_factory=dict)


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def perturb_search_chunk_hits(
    hits: list[dict],
    rng: random.Random,
    *,
    profile: BenchmarkRealismProfile,
) -> list[dict]:
    """Return a shallow-copied list of hit dicts (``search_chunks`` shape) after optional noise."""
    if not hits:
        return hits
    if rng.random() < profile.p_retrieval_empty:
        return []
    out = copy.deepcopy(hits)
    if len(out) >= 1 and rng.random() < profile.drop_top_chunk_probability:
        out = out[1:]
    if profile.shuffle_lower_ranks and len(out) >= 2:
        tail = out[1:]
        rng.shuffle(tail)
        out = [out[0]] + tail
    return out


def apply_heuristic_score_noise(
    retrieval_relevance: float | None,
    context_coverage: float | None,
    completeness: float | None,
    faithfulness: float | None,
    rng: random.Random,
    *,
    profile: BenchmarkRealismProfile,
) -> tuple[float | None, float | None, float | None, float | None]:
    """Add bounded uniform noise; keep faithfulness None for heuristic unless explicitly set."""

    def nudge(v: float | None) -> float | None:
        if v is None:
            return None
        d = profile.score_noise_max_delta
        return _clamp01(float(v) + rng.uniform(-d, d))

    return (
        nudge(retrieval_relevance),
        nudge(context_coverage),
        nudge(completeness),
        nudge(faithfulness),
    )


def classify_low_quality_failure(
    *,
    retrieval_relevance: float | None,
    context_coverage: float | None,
    completeness: float | None,
    current_failure: str,
    profile: BenchmarkRealismProfile,
) -> str:
    """Re-classify after noise — same priority as heuristic eval; thresholds from *profile*."""
    if current_failure == FailureType.RETRIEVAL_MISS.value:
        return current_failure
    if retrieval_relevance is not None and retrieval_relevance < profile.relevance_low_threshold:
        return FailureType.RETRIEVAL_PARTIAL.value
    if context_coverage is not None and context_coverage < profile.context_coverage_low_threshold:
        return FailureType.CONTEXT_INSUFFICIENT.value
    if completeness is not None and completeness < profile.completeness_low_threshold:
        return FailureType.ANSWER_INCOMPLETE.value
    return FailureType.NO_FAILURE.value
