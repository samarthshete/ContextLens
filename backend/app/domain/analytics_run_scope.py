"""Exclude synthetic benchmark-realism runs from analytics, comparisons, metrics, and summary.

Batch heuristic cells with :class:`~app.services.benchmark_realism.BenchmarkRealismProfile`
set ``runs.metadata_json['benchmark_realism']`` (truthy). Those runs are useful for stress
experiments but should not skew production-style dashboards, ``GET /runs/dashboard-summary``,
or ``aggregate.py`` reports.
"""

from __future__ import annotations

from typing import Any

# ``runs`` aliased as ``r`` in raw SQL (config comparison, aggregate.py).
SQL_RUNS_R_EXCLUDE_BENCHMARK_REALISM = "(r.metadata_json->>'benchmark_realism' IS NULL)"

# Unqualified ``runs`` table name (simple FROM runs …).
# **Note:** In SQLAlchemy ORM queries the table may be aliased (e.g. ``runs_1``); raw
# ``text("(runs.metadata_json ...")`` then fails to bind or applies to the wrong row.
# Use :func:`sqlalchemy_organic_run_clause` for ``select_from(Run)`` / joined ``Run``.
SQL_RUNS_TABLE_EXCLUDE_BENCHMARK_REALISM = "(runs.metadata_json->>'benchmark_realism' IS NULL)"


def sqlalchemy_organic_run_clause(run_entity: Any):
    """Same as ``metadata_json->>'benchmark_realism' IS NULL`` on the given ``Run`` mapper/alias.

    Use this in ORM ``where()`` clauses so the predicate tracks SQLAlchemy's table alias.
    """
    return run_entity.metadata_json["benchmark_realism"].astext.is_(None)
