"""Pure unit tests for batch realism helpers (no DB)."""

import random

import pytest

from app.domain.failure_taxonomy import FailureType
from app.services.benchmark_realism import (
    BenchmarkRealismProfile,
    apply_heuristic_score_noise,
    classify_low_quality_failure,
    perturb_search_chunk_hits,
)

pytestmark = pytest.mark.no_database_cleanup


def test_perturb_always_empty():
    p = BenchmarkRealismProfile(p_retrieval_empty=1.0)
    hits = [{"chunk_id": 1, "score": 0.9}]
    assert perturb_search_chunk_hits(hits, random.Random(1), profile=p) == []


def test_perturb_drop_top_deterministic():
    p = BenchmarkRealismProfile(
        drop_top_chunk_probability=1.0,
        shuffle_lower_ranks=False,
        p_retrieval_empty=0.0,
    )
    hits = [
        {"chunk_id": 1, "score": 0.9},
        {"chunk_id": 2, "score": 0.8},
    ]
    out = perturb_search_chunk_hits(hits, random.Random(42), profile=p)
    assert len(out) == 1
    assert out[0]["chunk_id"] == 2


def test_score_noise_bounded():
    p = BenchmarkRealismProfile(score_noise_max_delta=0.05)
    rng = random.Random(0)
    rr, cc, comp, ff = apply_heuristic_score_noise(0.5, 0.6, 0.7, None, rng, profile=p)
    assert ff is None
    for v in (rr, cc, comp):
        assert v is not None
        assert 0.0 <= v <= 1.0


def test_classify_low_relevance():
    p = BenchmarkRealismProfile(relevance_low_threshold=0.3)
    ft = classify_low_quality_failure(
        retrieval_relevance=0.1,
        context_coverage=0.9,
        completeness=0.9,
        current_failure="NO_FAILURE",
        profile=p,
    )
    assert ft == FailureType.RETRIEVAL_PARTIAL.value


def test_classify_low_coverage_after_relevance_ok():
    p = BenchmarkRealismProfile(
        relevance_low_threshold=0.3,
        context_coverage_low_threshold=0.4,
    )
    ft = classify_low_quality_failure(
        retrieval_relevance=0.8,
        context_coverage=0.1,
        completeness=0.9,
        current_failure="NO_FAILURE",
        profile=p,
    )
    assert ft == FailureType.CONTEXT_INSUFFICIENT.value


def test_classify_low_completeness_after_coverage_ok():
    p = BenchmarkRealismProfile(
        context_coverage_low_threshold=0.4,
        completeness_low_threshold=0.5,
    )
    ft = classify_low_quality_failure(
        retrieval_relevance=0.8,
        context_coverage=0.8,
        completeness=0.2,
        current_failure="NO_FAILURE",
        profile=p,
    )
    assert ft == FailureType.ANSWER_INCOMPLETE.value


def test_classify_retrieval_miss_preserved():
    p = BenchmarkRealismProfile()
    ft = classify_low_quality_failure(
        retrieval_relevance=0.1,
        context_coverage=0.1,
        completeness=0.1,
        current_failure=FailureType.RETRIEVAL_MISS.value,
        profile=p,
    )
    assert ft == FailureType.RETRIEVAL_MISS.value
