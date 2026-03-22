"""Compare pipeline configs using aggregated metrics from stored traced runs."""

from __future__ import annotations

from typing import Callable, Literal

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.evaluator_bucket import sql_is_heuristic_bucket, sql_is_llm_bucket
from app.schemas.config_comparison import (
    ConfigComparisonMetrics,
    ConfigComparisonResponse,
    ConfigScoreComparisonSummary,
)

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
  AVG(er.faithfulness)::double precision AS avg_faithfulness,
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


_SCORE_EPS = 1e-9


def _rank_avg_dimension(
    metrics: list[ConfigComparisonMetrics],
    get_val: Callable[[ConfigComparisonMetrics], float | None],
) -> tuple[int | None, int | None, float | None, float | None]:
    """Best / worst config ids and their bucket averages for one score column."""
    eligible: list[tuple[ConfigComparisonMetrics, float]] = []
    for m in metrics:
        if m.traced_runs <= 0:
            continue
        v = get_val(m)
        if v is None:
            continue
        eligible.append((m, float(v)))
    if not eligible:
        return None, None, None, None
    best_m, bv = max(eligible, key=lambda t: (t[1], -t[0].pipeline_config_id))
    worst_m, wv = min(eligible, key=lambda t: (t[1], t[0].pipeline_config_id))
    return best_m.pipeline_config_id, worst_m.pipeline_config_id, bv, wv


def _delta_pct(best_v: float, worst_v: float) -> float | None:
    if abs(best_v - worst_v) < _SCORE_EPS:
        return 0.0
    if worst_v > _SCORE_EPS:
        return 100.0 * (best_v - worst_v) / worst_v
    return None


def build_config_score_comparison(
    metrics: list[ConfigComparisonMetrics],
    *,
    include_faithfulness: bool,
) -> ConfigScoreComparisonSummary:
    """Summarize best/worst configs by average faithfulness and completeness in this bucket.

    When ``include_faithfulness`` is false (combined heuristic+LLM rows), faithfulness fields are
    all ``None`` — do not blend judge faithfulness with heuristic nulls.
    """
    bf: int | None = None
    wf: int | None = None
    faith_delta: float | None = None
    if include_faithfulness:
        bfv: float | None
        wfv: float | None
        bf, wf, bfv, wfv = _rank_avg_dimension(metrics, lambda m: m.avg_faithfulness)
        if bfv is not None and wfv is not None:
            faith_delta = _delta_pct(bfv, wfv)

    bc, wc, bcv, wcv = _rank_avg_dimension(metrics, lambda m: m.avg_completeness)
    comp_delta: float | None = None
    if bcv is not None and wcv is not None:
        comp_delta = _delta_pct(bcv, wcv)

    return ConfigScoreComparisonSummary(
        best_config_faithfulness=bf,
        worst_config_faithfulness=wf,
        faithfulness_delta_pct=faith_delta,
        best_config_completeness=bc,
        worst_config_completeness=wc,
        completeness_delta_pct=comp_delta,
    )


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
                    avg_faithfulness=None,
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
                avg_faithfulness=_float_or_none(m.get("avg_faithfulness")),
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
        rows = _build_metrics_list(pids, main, fails)
        return ConfigComparisonResponse(
            evaluator_type="combined",
            pipeline_config_ids=pids,
            configs=rows,
            buckets=None,
            score_comparison=build_config_score_comparison(rows, include_faithfulness=False),
            score_comparison_buckets=None,
        )

    if evaluator_type == "heuristic":
        main = await _query_main(session, pids, "heuristic")
        fails = await _query_failures(session, pids, "heuristic")
        rows = _build_metrics_list(pids, main, fails)
        return ConfigComparisonResponse(
            evaluator_type="heuristic",
            pipeline_config_ids=pids,
            configs=rows,
            buckets=None,
            score_comparison=build_config_score_comparison(rows, include_faithfulness=True),
            score_comparison_buckets=None,
        )

    if evaluator_type == "llm":
        main = await _query_main(session, pids, "llm")
        fails = await _query_failures(session, pids, "llm")
        rows = _build_metrics_list(pids, main, fails)
        return ConfigComparisonResponse(
            evaluator_type="llm",
            pipeline_config_ids=pids,
            configs=rows,
            buckets=None,
            score_comparison=build_config_score_comparison(rows, include_faithfulness=True),
            score_comparison_buckets=None,
        )

    # both buckets, separate rows
    main_h = await _query_main(session, pids, "heuristic")
    fail_h = await _query_failures(session, pids, "heuristic")
    main_l = await _query_main(session, pids, "llm")
    fail_l = await _query_failures(session, pids, "llm")
    list_h = _build_metrics_list(pids, main_h, fail_h)
    list_l = _build_metrics_list(pids, main_l, fail_l)
    return ConfigComparisonResponse(
        evaluator_type="both",
        pipeline_config_ids=pids,
        configs=None,
        buckets={
            "heuristic": list_h,
            "llm": list_l,
        },
        score_comparison=None,
        score_comparison_buckets={
            "heuristic": build_config_score_comparison(list_h, include_faithfulness=True),
            "llm": build_config_score_comparison(list_l, include_faithfulness=True),
        },
    )
