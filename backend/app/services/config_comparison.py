"""Compare pipeline configs using aggregated metrics from stored traced runs."""

from __future__ import annotations

from typing import Callable, Literal

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.benchmark_statistics import (
    RECOMMENDED_MIN_TRACED_RUNS_FOR_VALID_COMPARISON,
    RECOMMENDED_MIN_UNIQUE_QUERIES_FOR_VALID_COMPARISON,
    comparison_statistically_reliable_by_effective_sample,
    confidence_tier_from_effective_sample_size,
)
from app.domain.analytics_run_scope import SQL_RUNS_R_EXCLUDE_BENCHMARK_REALISM
from app.domain.evaluator_bucket import sql_is_heuristic_bucket, sql_is_llm_bucket
from app.domain.metric_display import round_metric_float
from app.schemas.config_comparison import (
    ConfigComparisonMetrics,
    ConfigComparisonResponse,
    ConfigScoreComparisonSummary,
)

_MAX_CONFIG_IDS = 64


def resolve_include_benchmark_realism_for_comparison(
    dataset_id: int | None,
    include_benchmark_realism: bool,
) -> bool:
    """Align with ``dashboard_aggregate_run_scope``: scoped comparisons include realism-tagged runs."""
    return include_benchmark_realism or (dataset_id is not None)

# Dataset scope matches ``dashboard_aggregate_run_scope``: filter via ``query_cases.dataset_id``.
_DATASET_FILTER = "  AND qc.dataset_id = :dataset_id"

# ``traced_runs`` / ``unique_query_count`` come from ``run_base`` only (retrieval + scope), not from
# whether an ``evaluation_results`` row exists or matches the evaluator bucket.
_MAIN_SQL = """
WITH run_base AS (
  SELECT
    r.id AS run_id,
    r.pipeline_config_id AS pipeline_config_id,
    r.query_case_id AS query_case_id,
    r.retrieval_latency_ms AS retrieval_latency_ms,
    r.evaluation_latency_ms AS evaluation_latency_ms,
    r.total_latency_ms AS total_latency_ms
  FROM runs r
  INNER JOIN query_cases qc ON qc.id = r.query_case_id
  WHERE r.pipeline_config_id IN :pids
    AND EXISTS (SELECT 1 FROM retrieval_results rr WHERE rr.run_id = r.id)
    AND {realism_filter}
    {dataset_filter}
),
eval_agg AS (
  SELECT
    er.run_id AS run_id,
    AVG(er.groundedness)::double precision AS groundedness,
    AVG(er.faithfulness)::double precision AS faithfulness,
    AVG(er.completeness)::double precision AS completeness,
    AVG(er.retrieval_relevance)::double precision AS retrieval_relevance,
    AVG(er.context_coverage)::double precision AS context_coverage,
    AVG(er.cost_usd::double precision)::double precision AS cost_usd
  FROM evaluation_results er
  INNER JOIN runs r ON r.id = er.run_id
  INNER JOIN query_cases qc ON qc.id = r.query_case_id
  WHERE r.pipeline_config_id IN :pids
    AND EXISTS (SELECT 1 FROM retrieval_results rr WHERE rr.run_id = r.id)
    AND {realism_filter}
    {dataset_filter}
{bucket_filter}
  GROUP BY er.run_id
)
SELECT
  rb.pipeline_config_id AS pipeline_config_id,
  COUNT(rb.run_id)::bigint AS traced_runs,
  COUNT(DISTINCT rb.query_case_id)::bigint AS unique_query_count,
  AVG(rb.retrieval_latency_ms)::double precision AS avg_retrieval_latency_ms,
  percentile_cont(0.95) WITHIN GROUP (ORDER BY rb.retrieval_latency_ms)::double precision
    AS p95_retrieval_latency_ms,
  AVG(rb.evaluation_latency_ms)::double precision AS avg_evaluation_latency_ms,
  percentile_cont(0.95) WITHIN GROUP (ORDER BY rb.evaluation_latency_ms)::double precision
    AS p95_evaluation_latency_ms,
  AVG(rb.total_latency_ms)::double precision AS avg_total_latency_ms,
  percentile_cont(0.95) WITHIN GROUP (ORDER BY rb.total_latency_ms)::double precision
    AS p95_total_latency_ms,
  AVG(ea.groundedness)::double precision AS avg_groundedness,
  AVG(ea.faithfulness)::double precision AS avg_faithfulness,
  AVG(ea.completeness)::double precision AS avg_completeness,
  AVG(ea.retrieval_relevance)::double precision AS avg_retrieval_relevance,
  AVG(ea.context_coverage)::double precision AS avg_context_coverage,
  AVG(ea.cost_usd)::double precision AS avg_evaluation_cost_per_run_usd,
  STDDEV_SAMP(ea.completeness)::double precision AS stddev_samp_completeness,
  STDDEV_SAMP(ea.faithfulness)::double precision AS stddev_samp_faithfulness,
  STDDEV_SAMP(ea.retrieval_relevance)::double precision AS stddev_samp_retrieval_relevance,
  STDDEV_SAMP(ea.context_coverage)::double precision AS stddev_samp_context_coverage,
  STDDEV_SAMP(rb.retrieval_latency_ms)::double precision AS stddev_samp_retrieval_latency_ms,
  STDDEV_SAMP(rb.total_latency_ms)::double precision AS stddev_samp_total_latency_ms
FROM run_base rb
LEFT JOIN eval_agg ea ON ea.run_id = rb.run_id
GROUP BY rb.pipeline_config_id
"""

_FAIL_SQL = """
SELECT
  r.pipeline_config_id AS pipeline_config_id,
  COALESCE(NULLIF(BTRIM(er.failure_type::text), ''), 'UNKNOWN') AS failure_type,
  COUNT(*)::bigint AS cnt
FROM runs r
INNER JOIN query_cases qc ON qc.id = r.query_case_id
INNER JOIN evaluation_results er ON er.run_id = r.id
WHERE r.pipeline_config_id IN :pids
  AND EXISTS (SELECT 1 FROM retrieval_results rr WHERE rr.run_id = r.id)
  AND {realism_filter}
  {dataset_filter}
{bucket_filter}
GROUP BY r.pipeline_config_id, COALESCE(NULLIF(BTRIM(er.failure_type::text), ''), 'UNKNOWN')
"""

_QUERY_SET_SQL = """
SELECT DISTINCT r.pipeline_config_id AS pipeline_config_id, r.query_case_id AS query_case_id
FROM runs r
INNER JOIN query_cases qc ON qc.id = r.query_case_id
WHERE r.pipeline_config_id IN :pids
  AND EXISTS (SELECT 1 FROM retrieval_results rr WHERE rr.run_id = r.id)
  AND {realism_filter}
  {dataset_filter}
"""


def _dataset_filter_sql(dataset_id: int | None) -> str:
    return _DATASET_FILTER if dataset_id is not None else ""


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


def _metric_float(v: object) -> float | None:
    return round_metric_float(_float_or_none(v))


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
    """Summarize best/worst configs by average faithfulness and completeness in this bucket."""
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
        faithfulness_delta_pct=round_metric_float(faith_delta),
        best_config_completeness=bc,
        worst_config_completeness=wc,
        completeness_delta_pct=round_metric_float(comp_delta),
    )


def _comparison_confidence_fields(rows: list[ConfigComparisonMetrics]) -> dict:
    if not rows:
        return {
            "comparison_confidence": "LOW",
            "comparison_statistically_reliable": False,
            "min_traced_runs_across_configs": 0,
            "recommended_min_traced_runs_for_valid_comparison": RECOMMENDED_MIN_TRACED_RUNS_FOR_VALID_COMPARISON,
            "unique_queries_compared": 0,
            "effective_sample_size": 0,
            "recommended_min_unique_queries_for_valid_comparison": RECOMMENDED_MIN_UNIQUE_QUERIES_FOR_VALID_COMPARISON,
        }
    m = min(r.traced_runs for r in rows)
    min_unique = min(r.unique_query_count for r in rows)
    effective = min_unique
    return {
        "comparison_confidence": confidence_tier_from_effective_sample_size(effective),
        "comparison_statistically_reliable": comparison_statistically_reliable_by_effective_sample(effective),
        "min_traced_runs_across_configs": m,
        "recommended_min_traced_runs_for_valid_comparison": RECOMMENDED_MIN_TRACED_RUNS_FOR_VALID_COMPARISON,
        "unique_queries_compared": effective,
        "effective_sample_size": effective,
        "recommended_min_unique_queries_for_valid_comparison": RECOMMENDED_MIN_UNIQUE_QUERIES_FOR_VALID_COMPARISON,
    }


def _exec_params(pids: list[int], dataset_id: int | None) -> dict:
    out: dict = {"pids": pids}
    if dataset_id is not None:
        out["dataset_id"] = dataset_id
    return out


def _realism_filter_sql(include_benchmark_realism: bool) -> str:
    if include_benchmark_realism:
        return "TRUE"
    return SQL_RUNS_R_EXCLUDE_BENCHMARK_REALISM


async def _query_main(
    session: AsyncSession,
    pids: list[int],
    bucket: Literal["llm", "heuristic"] | None,
    dataset_id: int | None,
    include_benchmark_realism: bool = False,
) -> dict[int, dict]:
    bf = _bucket_filter(bucket)
    ds = _dataset_filter_sql(dataset_id)
    stmt = text(
        _MAIN_SQL.format(
            dataset_filter=ds,
            bucket_filter=bf,
            realism_filter=_realism_filter_sql(include_benchmark_realism),
        )
    ).bindparams(
        bindparam("pids", expanding=True)
    )
    res = await session.execute(stmt, _exec_params(pids, dataset_id))
    return {int(row["pipeline_config_id"]): dict(row) for row in res.mappings()}


async def _query_failures(
    session: AsyncSession,
    pids: list[int],
    bucket: Literal["llm", "heuristic"] | None,
    dataset_id: int | None,
    include_benchmark_realism: bool = False,
) -> dict[int, dict[str, int]]:
    bf = _bucket_filter(bucket)
    ds = _dataset_filter_sql(dataset_id)
    stmt = text(
        _FAIL_SQL.format(
            dataset_filter=ds,
            bucket_filter=bf,
            realism_filter=_realism_filter_sql(include_benchmark_realism),
        )
    ).bindparams(
        bindparam("pids", expanding=True)
    )
    res = await session.execute(stmt, _exec_params(pids, dataset_id))
    acc: dict[int, dict[str, int]] = {}
    for row in res.mappings():
        pid = int(row["pipeline_config_id"])
        ft = str(row["failure_type"])
        acc.setdefault(pid, {})[ft] = int(row["cnt"])
    return acc


async def _query_query_case_sets(
    session: AsyncSession,
    pids: list[int],
    bucket: Literal["llm", "heuristic"] | None,
    dataset_id: int | None,
    include_benchmark_realism: bool = False,
) -> dict[int, frozenset[int]]:
    bf = _bucket_filter(bucket)
    ds = _dataset_filter_sql(dataset_id)
    stmt = text(
        _QUERY_SET_SQL.format(
            dataset_filter=ds,
            bucket_filter=bf,
            realism_filter=_realism_filter_sql(include_benchmark_realism),
        )
    ).bindparams(
        bindparam("pids", expanding=True)
    )
    res = await session.execute(stmt, _exec_params(pids, dataset_id))
    acc: dict[int, set[int]] = {pid: set() for pid in pids}
    for row in res.mappings():
        pid = int(row["pipeline_config_id"])
        qid = int(row["query_case_id"])
        acc.setdefault(pid, set()).add(qid)
    return {pid: frozenset(acc.get(pid, set())) for pid in pids}


def _enforce_integrity(
    pids: list[int],
    rows: list[ConfigComparisonMetrics],
    query_sets: dict[int, frozenset[int]],
    *,
    min_traced_runs: int | None,
    require_same_queries: bool,
) -> None:
    by_pid = {m.pipeline_config_id: m for m in rows}
    if require_same_queries and len(pids) >= 2:
        sets = [query_sets.get(pid, frozenset()) for pid in pids]
        if len(set(sets)) > 1:
            raise ValueError(
                "comparison integrity: distinct query_case_id sets differ across pipeline configs "
                f"(per-config query_case_ids: { {pid: sorted(query_sets.get(pid, frozenset())) for pid in pids} })"
            )
    if min_traced_runs is not None:
        for pid in pids:
            m = by_pid.get(pid)
            tr = m.traced_runs if m is not None else 0
            if tr < min_traced_runs:
                raise ValueError(
                    f"comparison integrity: pipeline_config_id={pid} has {tr} traced runs, "
                    f"requires >= {min_traced_runs}"
                )


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
                    unique_query_count=0,
                    avg_faithfulness=None,
                    failure_type_counts=dict(fmap),
                )
            )
            continue
        out.append(
            ConfigComparisonMetrics(
                pipeline_config_id=pid,
                traced_runs=int(m["traced_runs"]),
                unique_query_count=int(m["unique_query_count"]),
                avg_retrieval_latency_ms=_metric_float(m.get("avg_retrieval_latency_ms")),
                p95_retrieval_latency_ms=_metric_float(m.get("p95_retrieval_latency_ms")),
                avg_evaluation_latency_ms=_metric_float(m.get("avg_evaluation_latency_ms")),
                p95_evaluation_latency_ms=_metric_float(m.get("p95_evaluation_latency_ms")),
                avg_total_latency_ms=_metric_float(m.get("avg_total_latency_ms")),
                p95_total_latency_ms=_metric_float(m.get("p95_total_latency_ms")),
                avg_groundedness=_metric_float(m.get("avg_groundedness")),
                avg_faithfulness=_metric_float(m.get("avg_faithfulness")),
                avg_completeness=_metric_float(m.get("avg_completeness")),
                avg_retrieval_relevance=_metric_float(m.get("avg_retrieval_relevance")),
                avg_context_coverage=_metric_float(m.get("avg_context_coverage")),
                failure_type_counts=dict(fmap),
                avg_evaluation_cost_per_run_usd=_metric_float(m.get("avg_evaluation_cost_per_run_usd")),
                stddev_samp_completeness=_metric_float(m.get("stddev_samp_completeness")),
                stddev_samp_faithfulness=_metric_float(m.get("stddev_samp_faithfulness")),
                stddev_samp_retrieval_relevance=_metric_float(m.get("stddev_samp_retrieval_relevance")),
                stddev_samp_context_coverage=_metric_float(m.get("stddev_samp_context_coverage")),
                stddev_samp_retrieval_latency_ms=_metric_float(m.get("stddev_samp_retrieval_latency_ms")),
                stddev_samp_total_latency_ms=_metric_float(m.get("stddev_samp_total_latency_ms")),
            )
        )
    return out


async def compare_pipeline_configs(
    session: AsyncSession,
    pipeline_config_ids: list[int],
    *,
    evaluator_type: Literal["heuristic", "llm", "both"] = "both",
    dataset_id: int | None = None,
    min_traced_runs: int | None = None,
    strict_comparison: bool = False,
    include_benchmark_realism: bool = False,
) -> ConfigComparisonResponse:
    """Aggregate comparison metrics for the given config ids (order preserved).

    Heuristic and LLM buckets are always computed separately when ``evaluator_type`` is ``both``.
    Optional ``dataset_id`` restricts runs to that benchmark dataset's query cases.

    ``strict_comparison`` requires ``dataset_id``, enforces identical ``query_case_id`` coverage
    across all requested configs (within each bucket), and sets a default minimum of **2** traced
    runs per config unless ``min_traced_runs`` is higher.

    ``include_benchmark_realism``: when ``True``, runs tagged with
    ``metadata_json.benchmark_realism`` are **included** in the comparison (default: excluded).
    """
    pids = list(dict.fromkeys(pipeline_config_ids))
    if not pids:
        raise ValueError("pipeline_config_ids must not be empty")
    if len(pids) > _MAX_CONFIG_IDS:
        raise ValueError(f"at most {_MAX_CONFIG_IDS} pipeline_config_ids allowed")
    if strict_comparison and dataset_id is None:
        raise ValueError("strict_comparison requires dataset_id")

    effective_min: int | None = min_traced_runs
    if strict_comparison:
        effective_min = max(2, min_traced_runs or 2)
    require_same_q = strict_comparison

    ibr = resolve_include_benchmark_realism_for_comparison(dataset_id, include_benchmark_realism)

    if evaluator_type == "heuristic":
        qsets = await _query_query_case_sets(session, pids, "heuristic", dataset_id, ibr)
        main = await _query_main(session, pids, "heuristic", dataset_id, ibr)
        fails = await _query_failures(session, pids, "heuristic", dataset_id, ibr)
        rows = _build_metrics_list(pids, main, fails)
        _enforce_integrity(pids, rows, qsets, min_traced_runs=effective_min, require_same_queries=require_same_q)
        conf = _comparison_confidence_fields(rows)
        return ConfigComparisonResponse(
            evaluator_type="heuristic",
            pipeline_config_ids=pids,
            configs=rows,
            buckets=None,
            score_comparison=build_config_score_comparison(rows, include_faithfulness=True),
            score_comparison_buckets=None,
            dataset_id=dataset_id,
            strict_comparison_applied=strict_comparison,
            min_traced_runs_enforced=effective_min,
            **conf,
        )

    if evaluator_type == "llm":
        qsets = await _query_query_case_sets(session, pids, "llm", dataset_id, ibr)
        main = await _query_main(session, pids, "llm", dataset_id, ibr)
        fails = await _query_failures(session, pids, "llm", dataset_id, ibr)
        rows = _build_metrics_list(pids, main, fails)
        _enforce_integrity(pids, rows, qsets, min_traced_runs=effective_min, require_same_queries=require_same_q)
        conf = _comparison_confidence_fields(rows)
        return ConfigComparisonResponse(
            evaluator_type="llm",
            pipeline_config_ids=pids,
            configs=rows,
            buckets=None,
            score_comparison=build_config_score_comparison(rows, include_faithfulness=True),
            score_comparison_buckets=None,
            dataset_id=dataset_id,
            strict_comparison_applied=strict_comparison,
            min_traced_runs_enforced=effective_min,
            **conf,
        )

    main_h = await _query_main(session, pids, "heuristic", dataset_id, ibr)
    fail_h = await _query_failures(session, pids, "heuristic", dataset_id, ibr)
    main_l = await _query_main(session, pids, "llm", dataset_id, ibr)
    fail_l = await _query_failures(session, pids, "llm", dataset_id, ibr)
    list_h = _build_metrics_list(pids, main_h, fail_h)
    list_l = _build_metrics_list(pids, main_l, fail_l)
    qs_h = await _query_query_case_sets(session, pids, "heuristic", dataset_id, ibr)
    qs_l = await _query_query_case_sets(session, pids, "llm", dataset_id, ibr)
    _enforce_integrity(pids, list_h, qs_h, min_traced_runs=effective_min, require_same_queries=require_same_q)
    _enforce_integrity(pids, list_l, qs_l, min_traced_runs=effective_min, require_same_queries=require_same_q)
    conf = _comparison_confidence_fields(list_h + list_l)
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
        dataset_id=dataset_id,
        strict_comparison_applied=strict_comparison,
        min_traced_runs_enforced=effective_min,
        **conf,
    )
