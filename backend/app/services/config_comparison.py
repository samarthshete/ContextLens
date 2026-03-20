"""Compare pipeline configs using aggregated metrics from stored traced runs."""

from __future__ import annotations

from typing import Literal

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.evaluator_bucket import sql_is_heuristic_bucket, sql_is_llm_bucket
from app.schemas.config_comparison import ConfigComparisonMetrics, ConfigComparisonResponse

_MAX_CONFIG_IDS = 64

_MAIN_SQL = """
SELECT
  r.pipeline_config_id AS pipeline_config_id,
  COUNT(*)::bigint AS traced_runs,
  AVG(r.retrieval_latency_ms)::double precision AS avg_retrieval_latency_ms,
  percentile_cont(0.95) WITHIN GROUP (ORDER BY r.retrieval_latency_ms)::double precision
    AS p95_retrieval_latency_ms,
  AVG(r.evaluation_latency_ms)::double precision AS avg_evaluation_latency_ms,
  percentile_cont(0.95) WITHIN GROUP (ORDER BY r.evaluation_latency_ms)::double precision
    AS p95_evaluation_latency_ms,
  AVG(r.total_latency_ms)::double precision AS avg_total_latency_ms,
  percentile_cont(0.95) WITHIN GROUP (ORDER BY r.total_latency_ms)::double precision
    AS p95_total_latency_ms,
  AVG(er.groundedness)::double precision AS avg_groundedness,
  AVG(er.completeness)::double precision AS avg_completeness,
  AVG(er.retrieval_relevance)::double precision AS avg_retrieval_relevance,
  AVG(er.context_coverage)::double precision AS avg_context_coverage,
  AVG(er.cost_usd::double precision)::double precision AS avg_evaluation_cost_per_run_usd
FROM runs r
INNER JOIN evaluation_results er ON er.run_id = r.id
WHERE r.pipeline_config_id IN :pids
  AND EXISTS (SELECT 1 FROM retrieval_results rr WHERE rr.run_id = r.id)
{bucket_filter}
GROUP BY r.pipeline_config_id
"""

_FAIL_SQL = """
SELECT
  r.pipeline_config_id AS pipeline_config_id,
  COALESCE(er.failure_type, '') AS failure_type,
  COUNT(*)::bigint AS cnt
FROM runs r
INNER JOIN evaluation_results er ON er.run_id = r.id
WHERE r.pipeline_config_id IN :pids
  AND EXISTS (SELECT 1 FROM retrieval_results rr WHERE rr.run_id = r.id)
{bucket_filter}
GROUP BY r.pipeline_config_id, COALESCE(er.failure_type, '')
"""


def _bucket_filter(bucket: Literal["llm", "heuristic"] | None) -> str:
    if bucket == "llm":
        return f"  AND ({sql_is_llm_bucket('er')})"
    if bucket == "heuristic":
        return f"  AND ({sql_is_heuristic_bucket('er')})"
    return ""


def _float_or_none(v: object) -> float | None:
    if v is None:
        return None
    return float(v)


async def _query_main(
    session: AsyncSession,
    pids: list[int],
    bucket: Literal["llm", "heuristic"] | None,
) -> dict[int, dict]:
    bf = _bucket_filter(bucket)
    stmt = text(_MAIN_SQL.format(bucket_filter=bf)).bindparams(bindparam("pids", expanding=True))
    res = await session.execute(stmt, {"pids": pids})
    return {int(row["pipeline_config_id"]): dict(row) for row in res.mappings()}


async def _query_failures(
    session: AsyncSession,
    pids: list[int],
    bucket: Literal["llm", "heuristic"] | None,
) -> dict[int, dict[str, int]]:
    bf = _bucket_filter(bucket)
    stmt = text(_FAIL_SQL.format(bucket_filter=bf)).bindparams(bindparam("pids", expanding=True))
    res = await session.execute(stmt, {"pids": pids})
    acc: dict[int, dict[str, int]] = {}
    for row in res.mappings():
        pid = int(row["pipeline_config_id"])
        ft = row["failure_type"] if row["failure_type"] != "" else "(null)"
        acc.setdefault(pid, {})[str(ft)] = int(row["cnt"])
    return acc


def _build_metrics_list(
    pids: list[int],
    main: dict[int, dict],
    fails: dict[int, dict[str, int]],
) -> list[ConfigComparisonMetrics]:
    out: list[ConfigComparisonMetrics] = []
    for pid in pids:
        m = main.get(pid)
        fmap = fails.get(pid, {})
        if m is None:
            out.append(
                ConfigComparisonMetrics(
                    pipeline_config_id=pid,
                    traced_runs=0,
                    failure_type_counts=dict(fmap),
                )
            )
            continue
        out.append(
            ConfigComparisonMetrics(
                pipeline_config_id=pid,
                traced_runs=int(m["traced_runs"]),
                avg_retrieval_latency_ms=_float_or_none(m.get("avg_retrieval_latency_ms")),
                p95_retrieval_latency_ms=_float_or_none(m.get("p95_retrieval_latency_ms")),
                avg_evaluation_latency_ms=_float_or_none(m.get("avg_evaluation_latency_ms")),
                p95_evaluation_latency_ms=_float_or_none(m.get("p95_evaluation_latency_ms")),
                avg_total_latency_ms=_float_or_none(m.get("avg_total_latency_ms")),
                p95_total_latency_ms=_float_or_none(m.get("p95_total_latency_ms")),
                avg_groundedness=_float_or_none(m.get("avg_groundedness")),
                avg_completeness=_float_or_none(m.get("avg_completeness")),
                avg_retrieval_relevance=_float_or_none(m.get("avg_retrieval_relevance")),
                avg_context_coverage=_float_or_none(m.get("avg_context_coverage")),
                failure_type_counts=dict(fmap),
                avg_evaluation_cost_per_run_usd=_float_or_none(m.get("avg_evaluation_cost_per_run_usd")),
            )
        )
    return out


async def compare_pipeline_configs(
    session: AsyncSession,
    pipeline_config_ids: list[int],
    *,
    combine_evaluators: bool = False,
    evaluator_type: Literal["heuristic", "llm", "both"] = "both",
) -> ConfigComparisonResponse:
    """Aggregate comparison metrics for the given config ids (order preserved).

    Unless ``combine_evaluators`` is true, heuristic and LLM buckets are computed separately
    when ``evaluator_type`` is ``both``.
    """
    pids = list(dict.fromkeys(pipeline_config_ids))  # stable unique
    if not pids:
        raise ValueError("pipeline_config_ids must not be empty")
    if len(pids) > _MAX_CONFIG_IDS:
        raise ValueError(f"at most {_MAX_CONFIG_IDS} pipeline_config_ids allowed")

    if combine_evaluators:
        main = await _query_main(session, pids, None)
        fails = await _query_failures(session, pids, None)
        return ConfigComparisonResponse(
            evaluator_type="combined",
            pipeline_config_ids=pids,
            configs=_build_metrics_list(pids, main, fails),
            buckets=None,
        )

    if evaluator_type == "heuristic":
        main = await _query_main(session, pids, "heuristic")
        fails = await _query_failures(session, pids, "heuristic")
        return ConfigComparisonResponse(
            evaluator_type="heuristic",
            pipeline_config_ids=pids,
            configs=_build_metrics_list(pids, main, fails),
            buckets=None,
        )

    if evaluator_type == "llm":
        main = await _query_main(session, pids, "llm")
        fails = await _query_failures(session, pids, "llm")
        return ConfigComparisonResponse(
            evaluator_type="llm",
            pipeline_config_ids=pids,
            configs=_build_metrics_list(pids, main, fails),
            buckets=None,
        )

    # both buckets, separate rows
    main_h = await _query_main(session, pids, "heuristic")
    fail_h = await _query_failures(session, pids, "heuristic")
    main_l = await _query_main(session, pids, "llm")
    fail_l = await _query_failures(session, pids, "llm")
    return ConfigComparisonResponse(
        evaluator_type="both",
        pipeline_config_ids=pids,
        configs=None,
        buckets={
            "heuristic": _build_metrics_list(pids, main_h, fail_h),
            "llm": _build_metrics_list(pids, main_l, fail_l),
        },
    )
