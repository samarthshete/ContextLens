"""Unit tests for lexical helpers and heuristic failure classification."""

import pytest

from app.domain.failure_taxonomy import FailureType
from app.services.minimal_retrieval_evaluation import (
    classify_heuristic_failure_from_scores,
    hybrid_retrieval_gate_passes,
    significant_tokens,
    token_recall,
)

pytestmark = pytest.mark.no_database_cleanup


def test_significant_tokens_filters_short_and_case():
    assert significant_tokens("A bc DEF") == {"bc", "def"}


def test_token_recall_partial_match():
    q = significant_tokens("foo bar baz")
    r = token_recall(q, "Only foo appears here.")
    assert r is not None
    assert abs(r - 1 / 3) < 1e-6


def test_classify_heuristic_retrieval_miss():
    assert (
        classify_heuristic_failure_from_scores(
            retrieval_miss=True,
            retrieval_relevance=0.9,
            context_coverage=0.9,
            completeness=0.9,
        )
        == FailureType.RETRIEVAL_MISS.value
    )


def test_classify_heuristic_priority_relevance_then_coverage_then_completeness():
    assert (
        classify_heuristic_failure_from_scores(
            retrieval_miss=False,
            retrieval_relevance=0.2,
            context_coverage=0.1,
            completeness=0.1,
        )
        == FailureType.RETRIEVAL_PARTIAL.value
    )
    assert (
        classify_heuristic_failure_from_scores(
            retrieval_miss=False,
            retrieval_relevance=0.8,
            context_coverage=0.2,
            completeness=0.1,
        )
        == FailureType.CONTEXT_INSUFFICIENT.value
    )
    assert (
        classify_heuristic_failure_from_scores(
            retrieval_miss=False,
            retrieval_relevance=0.8,
            context_coverage=0.8,
            completeness=0.3,
        )
        == FailureType.ANSWER_INCOMPLETE.value
    )
    assert (
        classify_heuristic_failure_from_scores(
            retrieval_miss=False,
            retrieval_relevance=0.8,
            context_coverage=0.8,
            completeness=0.8,
        )
        == FailureType.NO_FAILURE.value
    )


def test_classify_heuristic_skips_none_scores():
    """Missing completeness (no expected_answer path) does not force ANSWER_INCOMPLETE."""
    assert (
        classify_heuristic_failure_from_scores(
            retrieval_miss=False,
            retrieval_relevance=0.8,
            context_coverage=0.8,
            completeness=None,
        )
        == FailureType.NO_FAILURE.value
    )


def test_hybrid_gate_requires_scores_and_thresholds():
    assert not hybrid_retrieval_gate_passes(
        max_chunk_score=0.9,
        retrieval_relevance=None,
        context_coverage=0.5,
    )
    assert not hybrid_retrieval_gate_passes(
        max_chunk_score=0.9,
        retrieval_relevance=0.6,
        context_coverage=None,
    )
    assert hybrid_retrieval_gate_passes(
        max_chunk_score=0.88,
        retrieval_relevance=0.55,
        context_coverage=0.42,
    )
    assert not hybrid_retrieval_gate_passes(
        max_chunk_score=0.87,
        retrieval_relevance=0.55,
        context_coverage=0.42,
    )
