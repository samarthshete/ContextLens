"""Optional benchmark-dataset filter for dashboard aggregates.

There is no ``runs.dataset_id`` column; runs tie to a benchmark dataset only through
``runs.query_case_id`` → ``query_cases.dataset_id`` — same as ``GET /api/v1/runs``.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select, true
from sqlalchemy.sql.elements import ColumnElement

from app.domain.analytics_run_scope import sqlalchemy_organic_run_clause
from app.models import QueryCase, Run


def dashboard_dataset_run_predicate(dataset_id: int | None) -> ColumnElement[Any]:
    """Restrict to runs whose query case belongs to *dataset_id*.

    When *dataset_id* is ``None``, no restriction (use with other predicates only).
    """
    if dataset_id is None:
        return true()
    return Run.query_case_id.in_(select(QueryCase.id).where(QueryCase.dataset_id == dataset_id))


def dashboard_aggregate_run_scope(run_entity: Any, dataset_id: int | None) -> ColumnElement[Any]:
    """SQL predicate for dashboard row counts, latency, cost, analytics, etc.

    - **Global** (``dataset_id is None``): exclude synthetic ``benchmark_realism`` batch
      rows only — same as historical dashboard / ``aggregate.py``-style reporting.
    - **Dataset-scoped** (``dataset_id`` set): **all** runs whose query case is in that
      dataset, **including** ``benchmark_realism`` runs — matches
      ``list_runs(..., dataset_id=...)`` / ``GET /runs?dataset_id=``.
    """
    if dataset_id is None:
        return sqlalchemy_organic_run_clause(run_entity)
    return run_entity.query_case_id.in_(
        select(QueryCase.id).where(QueryCase.dataset_id == dataset_id)
    )
