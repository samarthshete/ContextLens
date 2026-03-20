"""Failure taxonomy normalization."""

from app.domain.failure_taxonomy import FailureType, normalize_failure_type


def test_normalize_exact_enum_value():
    assert normalize_failure_type("RETRIEVAL_MISS") == FailureType.RETRIEVAL_MISS.value


def test_normalize_case_insensitive():
    assert normalize_failure_type("no_failure") == FailureType.NO_FAILURE.value


def test_normalize_empty_none():
    assert normalize_failure_type(None) is None
    assert normalize_failure_type("") is None


def test_normalize_unknown_to_unknown():
    assert normalize_failure_type("not_a_real_label") == FailureType.UNKNOWN.value
