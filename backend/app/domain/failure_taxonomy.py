"""Strict failure labels for ``evaluation_results.failure_type``.

Values are persisted as these exact strings. LLM judge output is normalized to this set;
unrecognized values become ``UNKNOWN``. Heuristic evaluators should use the same strings.
"""

from __future__ import annotations

from enum import StrEnum


class FailureType(StrEnum):
    NO_FAILURE = "NO_FAILURE"
    RETRIEVAL_MISS = "RETRIEVAL_MISS"
    RETRIEVAL_PARTIAL = "RETRIEVAL_PARTIAL"
    CHUNK_FRAGMENTATION = "CHUNK_FRAGMENTATION"
    # Heuristic: low context_coverage vs query (token recall in retrieved chunks).
    CONTEXT_INSUFFICIENT = "CONTEXT_INSUFFICIENT"
    CONTEXT_TRUNCATION = "CONTEXT_TRUNCATION"
    ANSWER_UNSUPPORTED = "ANSWER_UNSUPPORTED"
    ANSWER_INCOMPLETE = "ANSWER_INCOMPLETE"
    MIXED_FAILURE = "MIXED_FAILURE"
    UNKNOWN = "UNKNOWN"


ALLOWED_VALUES: frozenset[str] = frozenset(m.value for m in FailureType)


def normalize_failure_type(raw: str | None) -> str | None:
    """Return a valid taxonomy value, or ``None`` if *raw* is empty.

    Unknown non-empty strings map to ``UNKNOWN``.
    """
    if raw is None or not str(raw).strip():
        return None
    s = str(raw).strip()
    if s in ALLOWED_VALUES:
        return s
    sup = s.upper().replace(" ", "_")
    if sup in ALLOWED_VALUES:
        return sup
    aliases = {
        "NONE": FailureType.NO_FAILURE.value,
        "OK": FailureType.NO_FAILURE.value,
        "NO_FAILURES": FailureType.NO_FAILURE.value,
    }
    if sup in aliases:
        return aliases[sup]
    return FailureType.UNKNOWN.value


def failure_type_for_storage(raw: str | None) -> str:
    """Persisted ``evaluation_results.failure_type`` must never be SQL NULL.

    Empty / missing input maps to ``UNKNOWN`` (audit-safe). Callers that mean
    "successful run" should pass ``NO_FAILURE`` explicitly (see heuristic eval).
    """
    ft = normalize_failure_type(raw)
    return ft if ft is not None else FailureType.UNKNOWN.value
