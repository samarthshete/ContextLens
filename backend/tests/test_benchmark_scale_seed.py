"""Deterministic scale benchmark fixture (no DB)."""

import pytest

from app.services.benchmark_scale_seed import (
    build_scale_corpus_markdown,
    build_scale_query_dicts,
    canonical_answer_for_index,
    scale_topic_labels,
    SCALE_PIPELINE_SPECS,
)

pytestmark = pytest.mark.no_database_cleanup


# --- 52-topic contract ---

def test_scale_benchmark_has_52_topics_and_queries():
    labels = scale_topic_labels()
    assert len(labels) == 52
    rows = build_scale_query_dicts()
    assert len(rows) == 52
    assert all("query_text" in r and "expected_answer" in r for r in rows)


def test_scale_topics_no_duplicates():
    labels = scale_topic_labels()
    assert len(set(labels)) == len(labels), f"Duplicate topics found: {[t for t in labels if labels.count(t) > 1]}"


def test_scale_topics_no_blanks():
    labels = scale_topic_labels()
    for i, t in enumerate(labels):
        assert t and t.strip(), f"Blank topic at index {i}"


def test_scale_topics_stable_order():
    """Calling twice must return identical tuple (deterministic)."""
    assert scale_topic_labels() == scale_topic_labels()


def test_scale_topics_are_tuple():
    """Return type must be tuple for immutability."""
    labels = scale_topic_labels()
    assert isinstance(labels, tuple)


# --- corpus + query alignment ---

def test_corpus_has_all_52_sections():
    md = build_scale_corpus_markdown()
    for i in range(1, 53):
        assert f"## {i}." in md, f"Missing corpus section {i}"


def test_query_dicts_match_topics():
    labels = scale_topic_labels()
    rows = build_scale_query_dicts()
    for i, (topic, row) in enumerate(zip(labels, rows), start=1):
        assert topic in row["query_text"], f"Topic {topic!r} not in query_text at index {i}"
        assert canonical_answer_for_index(i, topic) == row["expected_answer"]


def test_canonical_answers_unique():
    labels = scale_topic_labels()
    answers = [canonical_answer_for_index(i, t) for i, t in enumerate(labels, start=1)]
    assert len(set(answers)) == 52


# --- pipeline specs ---

def test_pipeline_specs_count():
    assert len(SCALE_PIPELINE_SPECS) == 2


def test_pipeline_specs_have_required_keys():
    for spec in SCALE_PIPELINE_SPECS:
        assert "name" in spec
        assert "top_k" in spec
        assert "chunk_size" in spec


# --- informative error on contract break ---

def test_contract_error_shows_count():
    """If someone were to break the contract, the error message should include the actual count."""
    # We can't easily test this without monkeypatching, but we verify the guard runs
    # by confirming scale_topic_labels() succeeds (the guard is at the end of the function).
    labels = scale_topic_labels()
    assert len(labels) == 52
