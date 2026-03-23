"""Richer analytics aggregates from stored runs / evaluations (read-only)."""

from __future__ import annotations

from typing import Any, Literal

from sqlalchemy import func, not_, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.domain.analytics_run_scope import SQL_RUNS_TABLE_EXCLUDE_BENCHMARK_REALISM
from app.models import EvaluationResult, PipelineConfig, Run
from app.services.phase_latency_distribution import get_phase_latency_distribution
from app.schemas.dashboard_analytics import (
    ConfigInsight,
    ConfigInsightsByEvaluatorBucket,
    DashboardAnalyticsResponse,
    FailureAnalysisSection,
    FailureByConfig,
    LatencyDistributionSection,
    RecentFailedRun,
    TimeSeriesDay,
)


def _f(v: object | None) -> float | None:
    """Coerce Decimal / numeric DB result to float; None stays None."""
    if v is None:
        return None
    return float(v) if not isinstance(v, float) else v


async def _time_series(session: AsyncSession) -> list[TimeSeriesDay]:
    """Runs aggregated by calendar day (last 90 days max, newest first)."""
    date_col = func.date(Run.created_at).label("day")

    # Subquery: failure count per run (runs with a non-empty, non-NO_FAILURE failure_type)
    failure_sub = (
        select(EvaluationResult.run_id)
        .join(Run, Run.id == EvaluationResult.run_id)
        .where(
            EvaluationResult.failure_type.isnot(None),
            EvaluationResult.failure_type != "",
            EvaluationResult.failure_type != "NO_FAILURE",
            text(SQL_RUNS_TABLE_EXCLUDE_BENCHMARK_REALISM),
        )
    )

    # Per-run cost: SUM(cost_usd) grouped by run_id, so that if the schema
    # ever allows multiple evaluation rows per run the cost is aggregated at
    # the run level *before* being averaged into daily buckets.  This mirrors
    # the defensive pattern used in dashboard_summary.py for per-run LLM cost.
    run_cost_sq = (
        select(
            EvaluationResult.run_id.label("run_id"),
            func.sum(EvaluationResult.cost_usd).label("run_cost"),
        )
        .join(Run, Run.id == EvaluationResult.run_id)
        .where(
            EvaluationResult.cost_usd.isnot(None),
            text(SQL_RUNS_TABLE_EXCLUDE_BENCHMARK_REALISM),
        )
        .group_by(EvaluationResult.run_id)
    ).subquery("run_cost")

    # The main query no longer joins EvaluationResult directly — failure_sub
    # is an independent subquery, and cost comes from the pre-aggregated
    # run_cost_sq (one row per run, NULL when no measured cost).  This
    # eliminates any dependence on join multiplicity for cost averaging.
    stmt = (
        select(
            date_col,
            func.count(Run.id).label("runs"),
            func.count(Run.id).filter(Run.status == "completed").label("completed"),
            func.count(Run.id).filter(Run.status == "failed").label("failed"),
            func.avg(Run.total_latency_ms).filter(
                Run.total_latency_ms.isnot(None)
            ).label("avg_total_latency_ms"),
            func.avg(run_cost_sq.c.run_cost).label("avg_cost_usd"),
            func.count(Run.id).filter(Run.id.in_(failure_sub)).label("failure_count"),
        )
        .select_from(Run)
        .outerjoin(run_cost_sq, run_cost_sq.c.run_id == Run.id)
        .where(text(SQL_RUNS_TABLE_EXCLUDE_BENCHMARK_REALISM))
        .group_by(date_col)
        .order_by(date_col.desc())
        .limit(90)
    )
    rows = (await session.execute(stmt)).all()
    return [
        TimeSeriesDay(
            date=str(r.day),
            runs=int(r.runs),
            completed=int(r.completed),
            failed=int(r.failed),
            avg_total_latency_ms=_f(r.avg_total_latency_ms),
            avg_cost_usd=_f(r.avg_cost_usd),
            failure_count=int(r.failure_count),
        )
        for r in reversed(rows)  # oldest first for charting
    ]


async def _latency_distribution(session: AsyncSession) -> LatencyDistributionSection:
    """Min/max/avg/median/p95 for each latency phase (shared SQL via ``phase_latency_distribution``)."""

    excl = {"exclude_benchmark_realism_runs": True}
    return LatencyDistributionSection(
        retrieval=await get_phase_latency_distribution(session, Run.retrieval_latency_ms, **excl),
        generation=await get_phase_latency_distribution(session, Run.generation_latency_ms, **excl),
        evaluation=await get_phase_latency_distribution(session, Run.evaluation_latency_ms, **excl),
        total=await get_phase_latency_distribution(session, Run.total_latency_ms, **excl),
    )


async def _failure_analysis(session: AsyncSession) -> FailureAnalysisSection:
    """Overall failure counts/percentages, per-config breakdown, recent failed runs."""

    # Overall failure counts
    fail_rows = (
        await session.execute(
            select(EvaluationResult.failure_type, func.count())
            .join(Run, Run.id == EvaluationResult.run_id)
            .where(
                EvaluationResult.failure_type.isnot(None),
                EvaluationResult.failure_type != "",
                EvaluationResult.failure_type != "NO_FAILURE",
                text(SQL_RUNS_TABLE_EXCLUDE_BENCHMARK_REALISM),
            )
            .group_by(EvaluationResult.failure_type)
        )
    ).all()
    overall_counts = {str(ft): int(c) for ft, c in fail_rows}
    total_failures = sum(overall_counts.values())
    overall_percentages = (
        {k: round(v / total_failures * 100, 1) for k, v in overall_counts.items()}
        if total_failures > 0
        else {}
    )

    # Per-config failure breakdown
    config_fail_rows = (
        await session.execute(
            select(
                Run.pipeline_config_id,
                PipelineConfig.name,
                EvaluationResult.failure_type,
                func.count().label("cnt"),
            )
            .join(EvaluationResult, EvaluationResult.run_id == Run.id)
            .join(PipelineConfig, PipelineConfig.id == Run.pipeline_config_id)
            .where(
                EvaluationResult.failure_type.isnot(None),
                EvaluationResult.failure_type != "",
                EvaluationResult.failure_type != "NO_FAILURE",
                text(SQL_RUNS_TABLE_EXCLUDE_BENCHMARK_REALISM),
            )
            .group_by(Run.pipeline_config_id, PipelineConfig.name, EvaluationResult.failure_type)
            .order_by(Run.pipeline_config_id)
        )
    ).all()
    config_map: dict[int, FailureByConfig] = {}
    for pc_id, pc_name, ft, cnt in config_fail_rows:
        if pc_id not in config_map:
            config_map[pc_id] = FailureByConfig(
                pipeline_config_id=pc_id,
                pipeline_config_name=pc_name,
            )
        config_map[pc_id].failure_counts[str(ft)] = int(cnt)
        config_map[pc_id].total_failures += int(cnt)

    # Recent failed runs (last 10)
    recent_stmt = (
        select(Run.id, Run.status, Run.created_at, Run.pipeline_config_id, EvaluationResult.failure_type)
        .outerjoin(EvaluationResult, EvaluationResult.run_id == Run.id)
        .where(
            Run.status == "failed",
            text(SQL_RUNS_TABLE_EXCLUDE_BENCHMARK_REALISM),
        )
        .order_by(Run.created_at.desc(), Run.id.desc())
        .limit(10)
    )
    recent_rows = (await session.execute(recent_stmt)).all()
    recent_failed = [
        RecentFailedRun(
            run_id=r[0],
            status=r[1],
            created_at=str(r[2]),
            failure_type=r[4],
            pipeline_config_id=r[3],
        )
        for r in recent_rows
    ]

    return FailureAnalysisSection(
        overall_counts=overall_counts,
        overall_percentages=overall_percentages,
        by_config=list(config_map.values()),
        recent_failed_runs=recent_failed,
    )


def _evaluation_in_llm_bucket(er: Any) -> Any:
    """Match ``app.domain.evaluator_bucket`` SQL (LLM vs heuristic)."""
    return or_(
        er.used_llm_judge.is_(True),
        er.metadata_json["evaluator_type"].astext == "llm",
    )


async def _config_insights_for_bucket(
    session: AsyncSession,
    bucket: Literal["heuristic", "llm"],
) -> list[ConfigInsight]:
    """Per-config metrics for traced runs whose evaluation row is in *bucket* only."""

    er = aliased(EvaluationResult, name="er")
    bucket_pred = _evaluation_in_llm_bucket(er) if bucket == "llm" else not_(_evaluation_in_llm_bucket(er))

    # Per-run cost: only runs in this evaluator bucket (same bucket as score join).
    run_cost_sq = (
        select(
            er.run_id.label("run_id"),
            func.sum(er.cost_usd).label("run_cost"),
        )
        .select_from(er)
        .join(Run, Run.id == er.run_id)
        .where(
            er.cost_usd.isnot(None),
            bucket_pred,
            text(SQL_RUNS_TABLE_EXCLUDE_BENCHMARK_REALISM),
        )
        .group_by(er.run_id)
    ).subquery("run_cost")

    config_cost_sq = (
        select(
            Run.pipeline_config_id.label("pc_id"),
            func.avg(run_cost_sq.c.run_cost).label("avg_cost_usd"),
            func.sum(run_cost_sq.c.run_cost).label("total_cost_usd"),
        )
        .join(run_cost_sq, run_cost_sq.c.run_id == Run.id)
        .group_by(Run.pipeline_config_id)
    ).subquery("config_cost")

    stmt = (
        select(
            PipelineConfig.id,
            PipelineConfig.name,
            func.count(Run.id).label("traced_runs"),
            func.count().filter(Run.status == "completed").label("completed_runs"),
            func.count().filter(Run.status == "failed").label("failed_runs"),
            func.avg(Run.total_latency_ms).filter(
                Run.total_latency_ms.isnot(None)
            ).label("avg_total_latency_ms"),
            func.min(Run.total_latency_ms).label("min_total_latency_ms"),
            func.max(Run.total_latency_ms).label("max_total_latency_ms"),
            func.max(config_cost_sq.c.avg_cost_usd).label("avg_cost_usd"),
            func.max(config_cost_sq.c.total_cost_usd).label("total_cost_usd"),
            func.avg(er.retrieval_relevance).filter(er.retrieval_relevance.isnot(None)).label(
                "avg_retrieval_relevance"
            ),
            func.avg(er.context_coverage).filter(er.context_coverage.isnot(None)).label(
                "avg_context_coverage"
            ),
            func.avg(er.completeness).filter(er.completeness.isnot(None)).label("avg_completeness"),
            func.avg(er.faithfulness).filter(er.faithfulness.isnot(None)).label("avg_faithfulness"),
            func.max(Run.created_at).label("latest_run_at"),
        )
        .select_from(PipelineConfig)
        .join(Run, Run.pipeline_config_id == PipelineConfig.id)
        .join(er, er.run_id == Run.id)
        .where(bucket_pred)
        .outerjoin(config_cost_sq, config_cost_sq.c.pc_id == PipelineConfig.id)
        .group_by(PipelineConfig.id, PipelineConfig.name)
        .order_by(PipelineConfig.id)
    )
    rows = (await session.execute(stmt)).all()

    er_top = aliased(EvaluationResult, name="er_top")
    top_bucket = (
        _evaluation_in_llm_bucket(er_top) if bucket == "llm" else not_(_evaluation_in_llm_bucket(er_top))
    )
    top_fail_stmt = (
        select(
            Run.pipeline_config_id,
            er_top.failure_type,
            func.count().label("cnt"),
        )
        .select_from(Run)
        .join(er_top, er_top.run_id == Run.id)
        .where(
            top_bucket,
            er_top.failure_type.isnot(None),
            er_top.failure_type != "",
            er_top.failure_type != "NO_FAILURE",
            text(SQL_RUNS_TABLE_EXCLUDE_BENCHMARK_REALISM),
        )
        .group_by(Run.pipeline_config_id, er_top.failure_type)
    )
    top_fail_rows = (await session.execute(top_fail_stmt)).all()
    # Find top failure per config
    top_fail_map: dict[int, str] = {}
    max_counts: dict[int, int] = {}
    for pc_id, ft, cnt in top_fail_rows:
        cnt_int = int(cnt)
        if pc_id not in max_counts or cnt_int > max_counts[pc_id]:
            max_counts[pc_id] = cnt_int
            top_fail_map[pc_id] = str(ft)

    return [
        ConfigInsight(
            pipeline_config_id=r.id,
            pipeline_config_name=r.name,
            traced_runs=int(r.traced_runs),
            completed_runs=int(r.completed_runs),
            failed_runs=int(r.failed_runs),
            avg_total_latency_ms=_f(r.avg_total_latency_ms),
            min_total_latency_ms=_f(r.min_total_latency_ms),
            max_total_latency_ms=_f(r.max_total_latency_ms),
            avg_cost_usd=_f(r.avg_cost_usd),
            total_cost_usd=_f(r.total_cost_usd),
            avg_retrieval_relevance=_f(r.avg_retrieval_relevance),
            avg_context_coverage=_f(r.avg_context_coverage),
            avg_completeness=_f(r.avg_completeness),
            avg_faithfulness=_f(r.avg_faithfulness),
            latest_run_at=str(r.latest_run_at) if r.latest_run_at else None,
            top_failure_type=top_fail_map.get(r.id),
        )
        for r in rows
    ]


async def _config_insights(session: AsyncSession) -> ConfigInsightsByEvaluatorBucket:
    """Heuristic and LLM config insight rows — never blended."""
    heuristic = await _config_insights_for_bucket(session, "heuristic")
    llm = await _config_insights_for_bucket(session, "llm")
    return ConfigInsightsByEvaluatorBucket(heuristic=heuristic, llm=llm)


async def get_dashboard_analytics(session: AsyncSession) -> DashboardAnalyticsResponse:
    """Compute all analytics sections."""
    latency_distribution = await _latency_distribution(session)
    total = latency_distribution.total
    avg_sec: float | None = None
    p95_sec: float | None = None
    if total.count > 0:
        if total.avg_ms is not None:
            avg_sec = float(total.avg_ms) / 1000.0
        if total.p95_ms is not None:
            p95_sec = float(total.p95_ms) / 1000.0
    return DashboardAnalyticsResponse(
        time_series=await _time_series(session),
        latency_distribution=latency_distribution,
        end_to_end_run_latency_avg_sec=avg_sec,
        end_to_end_run_latency_p95_sec=p95_sec,
        failure_analysis=await _failure_analysis(session),
        config_insights=await _config_insights(session),
    )
