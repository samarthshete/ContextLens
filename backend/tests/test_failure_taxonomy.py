"""Failure taxonomy normalization."""

import pytest

from app.domain.failure_taxonomy import FailureType, failure_type_for_storage, normalize_failure_type

pytestmark = pytest.mark.no_database_cleanup


def test_normalize_exact_enum_value():
    assert normalize_failure_type("RETRIEVAL_MISS") == FailureType.RETRIEVAL_MISS.value


def test_normalize_case_insensitive():
    assert normalize_failure_type("no_failure") == FailureType.NO_FAILURE.value


def test_normalize_empty_none():
    assert normalize_failure_type(None) is None
    assert normalize_failure_type("") is None


def test_normalize_unknown_to_unknown():
    assert normalize_failure_type("not_a_real_label") == FailureType.UNKNOWN.value


def test_failure_type_for_storage_never_empty():
    assert failure_type_for_storage(None) == FailureType.UNKNOWN.value
    assert failure_type_for_storage("") == FailureType.UNKNOWN.value
    assert failure_type_for_storage("  ") == FailureType.UNKNOWN.value


def test_failure_type_for_storage_passthrough_valid():
    assert failure_type_for_storage("NO_FAILURE") == FailureType.NO_FAILURE.value


def test_normalize_context_insufficient():
    assert normalize_failure_type("context_insufficient") == FailureType.CONTEXT_INSUFFICIENT.value
