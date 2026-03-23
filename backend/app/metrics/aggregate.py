"""Aggregate ContextLens metrics from PostgreSQL — real rows only, no defaults.

Score averages and failure-type counts are **split by evaluator bucket** (heuristic vs LLM)
so heuristic and LLM judge rows are never blended in the same AVG.

**N/A (``None`` in Python / JSON, ``not available`` in generated Markdown)** vs **zero**:

- **Averages** (scores, latencies, ``avg_evaluation_cost_per_run_usd_*``): if no rows
  contribute non-NULL values to that metric, the aggregate is ``None`` — never coerced
  to ``0``.
- **Counts** (e.g. ``benchmark_datasets``, ``evaluation_rows_*``): ``0`` is a real
  count when SQL returns zero rows.
- **``llm_judge_call_rate``**: ``None`` when there are **no** ``evaluation_results``
  rows (denominator zero — undefined). If rows exist and none used the LLM judge,
  the rate is ``0.0`` (a real zero).
- **``cost_usd`` averages**: only rows with ``cost_usd IS NOT NULL`` participate;
  all-NULL in a bucket → ``None`` for that bucket's average (not ``0``).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.domain.analytics_run_scope import SQL_RUNS_R_EXCLUDE_BENCHMARK_REALISM
from app.domain.evaluator_bucket import SQL_IS_HEURISTIC_BUCKET, SQL_IS_LLM_BUCKET

REQUIRED_METRICS_TABLES = (
    "datasets",
    "query_cases",
    "pipeline_configs",
    "runs",
    "retrieval_results",
    "evaluation_results",
)


async def _table_exists(conn: AsyncConnection, name: str) -> bool:
    def sync_inspect(sync_conn):
        return inspect(sync_conn).has_table(name)

    return await conn.run_sync(lambda c: sync_inspect(c))


async def _scalar(conn: AsyncConnection, sql: str, params: dict | None = None) -> Any:
    row = (await conn.execute(text(sql), params or {})).one_or_none()
    if row is None:
        return None
    return row[0]


async def _failure_counts_for_bucket(
    conn: AsyncConnection,
    *,
    llm: bool,
) -> dict[str, int]:
    cond = SQL_IS_LLM_BUCKET if llm else SQL_IS_HEURISTIC_BUCKET
    excl = SQL_RUNS_R_EXCLUDE_BENCHMARK_REALISM
    rows = (
        (
            await conn.execute(
                text(
                    f"""
                    SELECT er.failure_type AS failure_type, COUNT(*) AS c
                    FROM evaluation_results er
                    INNER JOIN runs r ON r.id = er.run_id
                    WHERE er.failure_type IS NOT NULL AND er.failure_type <> ''
                      AND {cond}
                      AND {excl}
                    GROUP BY er.failure_type
                    ORDER BY er.failure_type
                    """
                )
            )
        )
        .mappings()
        .all()
    )
    return {r["failure_type"]: int(r["c"]) for r in rows} if rows else {}


async def aggregate_all_metrics(conn: AsyncConnection) -> dict[str, Any]:
    """Return metric keys for Markdown / JSON.

    **Evaluator buckets (see ``app/domain/evaluator_bucket.py``):**
    - *LLM:* ``used_llm_judge`` OR ``metadata_json.evaluator_type == 'llm'``
    - *Heuristic:* otherwise

    Blended score averages (``avg_faithfulness`` without suffix) are **omitted** to avoid
    silent mixing; use ``avg_*_llm`` and ``avg_*_heuristic``.
    """
    out: dict[str, Any] = {}

    if await _table_exists(conn, "documents"):
        out["document_count"] = await _scalar(conn, "SELECT COUNT(*) FROM documents")
    else:
        out["document_count"] = None

    if await _table_exists(conn, "chunks"):
        out["chunk_count"] = await _scalar(conn, "SELECT COUNT(*) FROM chunks")
    else:
        out["chunk_count"] = None

    missing = [t for t in REQUIRED_METRICS_TABLES if not await _table_exists(conn, t)]
    if missing:
        out["_missing_tables"] = missing
        return out

    llm_cond_er = SQL_IS_LLM_BUCKET
    heur_cond_er = SQL_IS_HEURISTIC_BUCKET

    out["benchmark_datasets"] = await _scalar(conn, "SELECT COUNT(*) FROM datasets")
    out["total_queries"] = await _scalar(conn, "SELECT COUNT(*) FROM query_cases")
    excl = SQL_RUNS_R_EXCLUDE_BENCHMARK_REALISM
    out["configs_tested"] = await _scalar(
        conn,
        f"SELECT COUNT(DISTINCT pipeline_config_id) FROM runs r WHERE {excl}",
    )

    out["total_traced_runs"] = await _scalar(
        conn,
        f"""
        SELECT COUNT(*) FROM runs r
        WHERE {excl}
          AND EXISTS (SELECT 1 FROM retrieval_results rr WHERE rr.run_id = r.id)
          AND EXISTS (SELECT 1 FROM evaluation_results er WHERE er.run_id = r.id)
        """,
    )

    out["total_traced_runs_llm"] = await _scalar(
        conn,
        f"""
        SELECT COUNT(*) FROM runs r
        WHERE {excl}
          AND EXISTS (SELECT 1 FROM retrieval_results rr WHERE rr.run_id = r.id)
          AND EXISTS (
            SELECT 1 FROM evaluation_results er
            WHERE er.run_id = r.id AND {llm_cond_er}
          )
        """,
    )
    out["total_traced_runs_heuristic"] = await _scalar(
        conn,
        f"""
        SELECT COUNT(*) FROM runs r
        WHERE {excl}
          AND EXISTS (SELECT 1 FROM retrieval_results rr WHERE rr.run_id = r.id)
          AND EXISTS (
            SELECT 1 FROM evaluation_results er
            WHERE er.run_id = r.id AND {heur_cond_er}
          )
        """,
    )

    out["evaluation_rows_llm"] = await _scalar(
        conn,
        f"""
        SELECT COUNT(*) FROM evaluation_results er
        INNER JOIN runs r ON r.id = er.run_id
        WHERE {llm_cond_er} AND {excl}
        """,
    )
    out["evaluation_rows_heuristic"] = await _scalar(
        conn,
        f"""
        SELECT COUNT(*) FROM evaluation_results er
        INNER JOIN runs r ON r.id = er.run_id
        WHERE {heur_cond_er} AND {excl}
        """,
    )

    # Latencies: global = any run with non-NULL column (may mix evaluator types).
    for col in (
        "retrieval_latency_ms",
        "generation_latency_ms",
        "evaluation_latency_ms",
        "total_latency_ms",
    ):
        n = await _scalar(
            conn,
            f"SELECT COUNT(*) FROM runs r WHERE r.{col} IS NOT NULL AND {excl}",
        )
        prefix = col.replace("_latency_ms", "")
        if not n:
            out[f"avg_{prefix}_latency_ms"] = None
            out[f"p95_{prefix}_latency_ms"] = None
        else:
            out[f"avg_{prefix}_latency_ms"] = await _scalar(
                conn,
                f"SELECT AVG(r.{col})::float FROM runs r WHERE r.{col} IS NOT NULL AND {excl}",
            )
            out[f"p95_{prefix}_latency_ms"] = await _scalar(
                conn,
                f"""
                SELECT percentile_cont(0.95) WITHIN GROUP (ORDER BY r.{col})::float
                FROM runs r
                WHERE r.{col} IS NOT NULL AND {excl}
                """,
            )

    # Split latencies: join runs to evaluation bucket.
    for phase_key, col in (
        ("evaluation", "evaluation_latency_ms"),
        ("total", "total_latency_ms"),
    ):
        for bucket, cond in (("llm", llm_cond_er), ("heuristic", heur_cond_er)):
            n = await _scalar(
                conn,
                f"""
                SELECT COUNT(*) FROM runs r
                INNER JOIN evaluation_results er ON er.run_id = r.id
                WHERE r.{col} IS NOT NULL AND {cond} AND {excl}
                """,
            )
            b = bucket
            if not n:
                out[f"avg_{phase_key}_latency_ms_{b}"] = None
                out[f"p95_{phase_key}_latency_ms_{b}"] = None
            else:
                out[f"avg_{phase_key}_latency_ms_{b}"] = await _scalar(
                    conn,
                    f"""
                    SELECT AVG(r.{col})::float FROM runs r
                    INNER JOIN evaluation_results er ON er.run_id = r.id
                    WHERE r.{col} IS NOT NULL AND {cond} AND {excl}
                    """,
                )
                out[f"p95_{phase_key}_latency_ms_{b}"] = await _scalar(
                    conn,
                    f"""
                    SELECT percentile_cont(0.95) WITHIN GROUP (ORDER BY r.{col})::float
                    FROM runs r
                    INNER JOIN evaluation_results er ON er.run_id = r.id
                    WHERE r.{col} IS NOT NULL AND {cond} AND {excl}
                    """,
                )

    score_cols = (
        "faithfulness",
        "completeness",
        "retrieval_relevance",
        "context_coverage",
        "groundedness",
    )
    for col in score_cols:
        for bucket, cond in (("llm", llm_cond_er), ("heuristic", heur_cond_er)):
            n = await _scalar(
                conn,
                f"""
                SELECT COUNT(*) FROM evaluation_results er
                INNER JOIN runs r ON r.id = er.run_id
                WHERE er.{col} IS NOT NULL AND {cond} AND {excl}
                """,
            )
            suffix = f"_{bucket}"
            if not n:
                out[f"avg_{col}{suffix}"] = None
            else:
                out[f"avg_{col}{suffix}"] = await _scalar(
                    conn,
                    f"""
                    SELECT AVG(er.{col})::float FROM evaluation_results er
                    INNER JOIN runs r ON r.id = er.run_id
                    WHERE er.{col} IS NOT NULL AND {cond} AND {excl}
                    """,
                )

    out["failure_type_counts_llm"] = await _failure_counts_for_bucket(conn, llm=True)
    out["failure_type_counts_heuristic"] = await _failure_counts_for_bucket(conn, llm=False)

    rows_all = (
        (
            await conn.execute(
                text(
                    """
                    SELECT failure_type, COUNT(*) AS c
                    FROM evaluation_results
                    WHERE failure_type IS NOT NULL AND failure_type <> ''
                    GROUP BY failure_type
                    ORDER BY failure_type
                    """
                )
            )
        )
        .mappings()
        .all()
    )
    out["failure_type_counts_all"] = (
        {r["failure_type"]: int(r["c"]) for r in rows_all} if rows_all else {}
    )

    # Cost: never blend across buckets in a single average — report per bucket.
    for bucket, cond in (("llm", llm_cond_er), ("heuristic", heur_cond_er)):
        n_cost = await _scalar(
            conn,
            f"""
            SELECT COUNT(*) FROM evaluation_results er
            INNER JOIN runs r ON r.id = er.run_id
            WHERE er.cost_usd IS NOT NULL AND {cond} AND {excl}
            """,
        )
        key = f"avg_evaluation_cost_per_run_usd_{bucket}"
        if not n_cost:
            out[key] = None
        else:
            out[key] = await _scalar(
                conn,
                f"""
                SELECT AVG(er.cost_usd) FROM evaluation_results er
                INNER JOIN runs r ON r.id = er.run_id
                WHERE er.cost_usd IS NOT NULL AND {cond} AND {excl}
                """,
            )

    # Ratio over all evaluation rows; undefined (N/A) when denominator is 0.
    n_eval = await _scalar(
        conn,
        f"""
        SELECT COUNT(*) FROM evaluation_results er
        INNER JOIN runs r ON r.id = er.run_id
        WHERE {excl}
        """,
    )
    if not n_eval:
        out["llm_judge_call_rate"] = None
    else:
        with_llm = await _scalar(
            conn,
            f"""
            SELECT COUNT(*) FROM evaluation_results er
            INNER JOIN runs r ON r.id = er.run_id
            WHERE er.used_llm_judge IS TRUE AND {excl}
            """,
        )
        out["llm_judge_call_rate"] = float(with_llm) / float(n_eval)

    return out
