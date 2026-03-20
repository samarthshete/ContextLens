"""Classify evaluation rows as *llm* vs *heuristic* for metrics (same logic everywhere).

**LLM bucket:** ``used_llm_judge IS TRUE`` OR ``metadata_json->>'evaluator_type' = 'llm'``.

**Heuristic bucket:** everything else (including legacy rows with no ``evaluator_type`` and
``used_llm_judge`` false).
"""

from __future__ import annotations


def sql_is_llm_bucket(alias: str = "er") -> str:
    return (
        f"(({alias}.used_llm_judge IS TRUE) OR ({alias}.metadata_json->>'evaluator_type' = 'llm'))"
    )


def sql_is_heuristic_bucket(alias: str = "er") -> str:
    return f"(NOT {sql_is_llm_bucket(alias)})"


# Backwards-compatible names (alias ``er`` — used in ``aggregate.py`` SQL strings)
SQL_IS_LLM_BUCKET = sql_is_llm_bucket("er")
SQL_IS_HEURISTIC_BUCKET = sql_is_heuristic_bucket("er")


def resolved_evaluator_type(*, used_llm_judge: bool, metadata_json: dict | None) -> str:
    """Return ``\"llm\"`` or ``\"heuristic\"`` for API / run detail (Python mirror of SQL)."""
    meta = metadata_json or {}
    if used_llm_judge or meta.get("evaluator_type") == "llm":
        return "llm"
    return "heuristic"
