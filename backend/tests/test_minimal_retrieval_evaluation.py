"""Unit tests for lexical helpers used by the minimal retrieval evaluator."""

from app.services.minimal_retrieval_evaluation import significant_tokens, token_recall


def test_significant_tokens_filters_short_and_case():
    assert significant_tokens("A bc DEF") == {"bc", "def"}


def test_token_recall_partial_match():
    q = significant_tokens("foo bar baz")
    r = token_recall(q, "Only foo appears here.")
    assert r is not None
    assert abs(r - 1 / 3) < 1e-6
