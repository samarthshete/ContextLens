"""Aggregate dashboard metrics from stored runs / evaluations (read-only)."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import exists, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.evaluator_bucket import (
    resolved_evaluator_type,
    sql_is_heuristic_bucket,
    sql_is_llm_bucket,
)
from app.models import Chunk, Dataset, Document, EvaluationResult, GenerationResult, QueryCase, RetrievalResult, Run
from app.services.phase_latency_distribution import get_phase_latency_distribution
from app.schemas.dashboard_summary import (
    DashboardCostSummary,
    DashboardEvaluatorCounts,
    DashboardLatencySummary,
    DashboardRecentRun,
    DashboardScaleMetrics,
    DashboardStatusCounts,
    DashboardSummaryResponse,
)


def _favg(v: object | None) -> float | None:
    """Coerce Decimal / numeric DB result to float; None stays None."""
    if v is None:
        return None
    return float(v)


def _ms_to_sec(ms: float | None) -> float | None:
    """Convert aggregate milliseconds to seconds; ``None`` = not measured / no samples."""
    if ms is None:
        return None
    return float(ms) / 1000.0


async def get_dashboard_summary(session: AsyncSession) -> DashboardSummaryResponse:
    total_runs = int(await session.scalar(select(func.count()).select_from(Run)) or 0)

    completed = int(
        await session.scalar(select(func.count()).select_from(Run).where(Run.status == "completed"))
        or 0
    )
    failed = int(
        await session.scalar(select(func.count()).select_from(Run).where(Run.status == "failed")) or 0
    )
    in_progress = int(
        await session.scalar(
            select(func.count()).select_from(Run).where(Run.status.not_in(("completed", "failed")))
        )
        or 0
    )

    heur_sql = sql_is_heuristic_bucket("evaluation_results")
    llm_sql = sql_is_llm_bucket("evaluation_results")

    heuristic_runs = int(
        await session.scalar(
            select(func.count(func.distinct(Run.id)))
            .select_from(Run)
            .join(EvaluationResult, EvaluationResult.run_id == Run.id)
            .where(text(f"({heur_sql})"))
        )
        or 0
    )
    llm_runs = int(
        await session.scalar(
            select(func.count(func.distinct(Run.id)))
            .select_from(Run)
            .join(EvaluationResult, EvaluationResult.run_id == Run.id)
            .where(text(f"({llm_sql})"))
        )
        or 0
    )
    runs_without_evaluation = int(
        await session.scalar(
            select(func.count())
            .select_from(Run)
            .outerjoin(EvaluationResult, EvaluationResult.run_id == Run.id)
            .where(EvaluationResult.id.is_(None))
        )
        or 0
    )

    benchmark_datasets = int(await session.scalar(select(func.count()).select_from(Dataset)) or 0)
    total_queries = int(await session.scalar(select(func.count()).select_from(QueryCase)) or 0)
    total_traced_runs = int(
        await session.scalar(
            select(func.count())
            .select_from(Run)
            .where(
                exists(select(1).select_from(RetrievalResult).where(RetrievalResult.run_id == Run.id)),
                exists(select(1).select_from(EvaluationResult).where(EvaluationResult.run_id == Run.id)),
            )
        )
        or 0
    )
    configs_tested = int(
        await session.scalar(select(func.count(func.distinct(Run.pipeline_config_id))).select_from(Run)) or 0
    )
    documents_processed = int(
        await session.scalar(
            select(func.count()).select_from(Document).where(Document.status == "processed")
        )
        or 0
    )
    chunks_indexed = int(await session.scalar(select(func.count()).select_from(Chunk)) or 0)

    retrieval_dist = await get_phase_latency_distribution(session, Run.retrieval_latency_ms)
    total_dist = await get_phase_latency_distribution(session, Run.total_latency_ms)
    avg_gen = await session.scalar(
        select(func.avg(Run.generation_latency_ms)).where(Run.generation_latency_ms.isnot(None))
    )
    avg_ev = await session.scalar(
        select(func.avg(Run.evaluation_latency_ms)).where(Run.evaluation_latency_ms.isnot(None))
    )

    total_cost = await session.scalar(
        select(func.sum(EvaluationResult.cost_usd)).where(EvaluationResult.cost_usd.isnot(None))
    )
    avg_cost = await session.scalar(
        select(func.avg(EvaluationResult.cost_usd)).where(EvaluationResult.cost_usd.isnot(None))
    )
    with_cost = int(
        await session.scalar(
            select(func.count()).select_from(EvaluationResult).where(EvaluationResult.cost_usd.isnot(None))
        )
        or 0
    )
    cost_na = int(
        await session.scalar(
            select(func.count()).select_from(EvaluationResult).where(EvaluationResult.cost_usd.is_(None))
        )
        or 0
    )

    # Per-**run** averages: SUM(cost) grouped by run_id, then AVG (honest if multiple eval rows per run).
    er_llm_bucket = text(f"({sql_is_llm_bucket('evaluation_results')})")
    llm_cost_per_run_sq = (
        select(
            EvaluationResult.run_id.label("run_id"),
            func.sum(EvaluationResult.cost_usd).label("run_cost"),
        )
        .where(EvaluationResult.cost_usd.isnot(None), er_llm_bucket)
        .group_by(EvaluationResult.run_id)
    ).subquery()
    avg_cost_per_llm_run = await session.scalar(
        select(func.avg(llm_cost_per_run_sq.c.run_cost)).select_from(llm_cost_per_run_sq)
    )
    llm_runs_with_measured_cost = int(
        await session.scalar(select(func.count()).select_from(llm_cost_per_run_sq)) or 0
    )

    full_rag_llm_cost_sq = (
        select(
            EvaluationResult.run_id.label("run_id"),
            func.sum(EvaluationResult.cost_usd).label("run_cost"),
        )
        .where(
            EvaluationResult.cost_usd.isnot(None),
            er_llm_bucket,
            exists(
                select(1)
                .select_from(GenerationResult)
                .where(GenerationResult.run_id == EvaluationResult.run_id)
            ),
        )
        .group_by(EvaluationResult.run_id)
    ).subquery()
    avg_cost_per_full_rag_run = await session.scalar(
        select(func.avg(full_rag_llm_cost_sq.c.run_cost)).select_from(full_rag_llm_cost_sq)
    )
    full_rag_runs_with_measured_cost = int(
        await session.scalar(select(func.count()).select_from(full_rag_llm_cost_sq)) or 0
    )

    fail_rows = (
        await session.execute(
            select(EvaluationResult.failure_type, func.count())
            .where(
                EvaluationResult.failure_type.isnot(None),
                EvaluationResult.failure_type != "",
            )
            .group_by(EvaluationResult.failure_type)
        )
    ).all()
    failure_type_counts = {str(ft): int(c) for ft, c in fail_rows if ft is not None}

    recent_stmt = (
        select(Run, EvaluationResult, QueryCase)
        .join(QueryCase, Run.query_case_id == QueryCase.id)
        .outerjoin(EvaluationResult, EvaluationResult.run_id == Run.id)
        .order_by(Run.created_at.desc(), Run.id.desc())
        .limit(20)
    )
    recent_result = await session.execute(recent_stmt)
    recent_runs: list[DashboardRecentRun] = []
    for run, ev, _qc in recent_result.all():
        ev_type: str = "none"
        cost_usd: float | None = None
        failure_type: str | None = None
        if ev is not None:
            ev_type = resolved_evaluator_type(
                used_llm_judge=bool(ev.used_llm_judge),
                metadata_json=ev.metadata_json,
            )
            cost_usd = _favg(ev.cost_usd)
            failure_type = ev.failure_type or None
        recent_runs.append(
            DashboardRecentRun(
                run_id=run.id,
                status=run.status,
                created_at=run.created_at,
                evaluator_type=ev_type,  # type: ignore[arg-type]
                total_latency_ms=run.total_latency_ms,
                cost_usd=cost_usd,
                failure_type=failure_type,
            )
        )

    return DashboardSummaryResponse(
        total_runs=total_runs,
        scale=DashboardScaleMetrics(
            benchmark_datasets=benchmark_datasets,
            total_queries=total_queries,
            total_traced_runs=total_traced_runs,
            configs_tested=configs_tested,
            documents_processed=documents_processed,
            chunks_indexed=chunks_indexed,
        ),
        status_counts=DashboardStatusCounts(
            completed=completed,
            failed=failed,
            in_progress=in_progress,
        ),
        evaluator_counts=DashboardEvaluatorCounts(
            heuristic_runs=heuristic_runs,
            llm_runs=llm_runs,
            runs_without_evaluation=runs_without_evaluation,
        ),
        latency=DashboardLatencySummary(
            avg_retrieval_latency_ms=_favg(retrieval_dist.avg_ms),
            retrieval_latency_p50_ms=_favg(retrieval_dist.median_ms),
            retrieval_latency_p95_ms=_favg(retrieval_dist.p95_ms),
            avg_generation_latency_ms=_favg(avg_gen),
            avg_evaluation_latency_ms=_favg(avg_ev),
            avg_total_latency_ms=_favg(total_dist.avg_ms),
            end_to_end_run_latency_avg_sec=_ms_to_sec(total_dist.avg_ms),
            end_to_end_run_latency_p95_sec=_ms_to_sec(total_dist.p95_ms),
        ),
        cost=DashboardCostSummary(
            total_cost_usd=_favg(total_cost),
            avg_cost_usd=_favg(avg_cost),
            evaluation_rows_with_cost=with_cost,
            evaluation_rows_cost_not_available=cost_na,
            avg_cost_usd_per_llm_run=_favg(avg_cost_per_llm_run),
            llm_runs_with_measured_cost=llm_runs_with_measured_cost,
            avg_cost_usd_per_full_rag_run=_favg(avg_cost_per_full_rag_run),
            full_rag_runs_with_measured_cost=full_rag_runs_with_measured_cost,
        ),
        failure_type_counts=failure_type_counts,
        recent_runs=recent_runs,
    )
