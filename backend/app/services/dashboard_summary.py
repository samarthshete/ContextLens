"""Aggregate dashboard metrics from stored runs / evaluations (read-only)."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.evaluator_bucket import resolved_evaluator_type, sql_is_heuristic_bucket, sql_is_llm_bucket
from app.models import EvaluationResult, QueryCase, Run
from app.schemas.dashboard_summary import (
    DashboardCostSummary,
    DashboardEvaluatorCounts,
    DashboardLatencySummary,
    DashboardRecentRun,
    DashboardStatusCounts,
    DashboardSummaryResponse,
)


def _favg(v: object | None) -> float | None:
    if v is None:
        return None
    if isinstance(v, Decimal):
        return float(v)
    return float(v)


def _f_or_none(v: object | None) -> float | None:
    if v is None:
        return None
    if isinstance(v, Decimal):
        x = float(v)
    else:
        x = float(v)
    return x


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

    avg_ret = await session.scalar(
        select(func.avg(Run.retrieval_latency_ms)).where(Run.retrieval_latency_ms.isnot(None))
    )
    avg_gen = await session.scalar(
        select(func.avg(Run.generation_latency_ms)).where(Run.generation_latency_ms.isnot(None))
    )
    avg_ev = await session.scalar(
        select(func.avg(Run.evaluation_latency_ms)).where(Run.evaluation_latency_ms.isnot(None))
    )
    avg_tot = await session.scalar(
        select(func.avg(Run.total_latency_ms)).where(Run.total_latency_ms.isnot(None))
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
            cost_usd = _f_or_none(ev.cost_usd)
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
            avg_retrieval_latency_ms=_favg(avg_ret),
            avg_generation_latency_ms=_favg(avg_gen),
            avg_evaluation_latency_ms=_favg(avg_ev),
            avg_total_latency_ms=_favg(avg_tot),
        ),
        cost=DashboardCostSummary(
            total_cost_usd=_f_or_none(total_cost),
            avg_cost_usd=_favg(avg_cost),
            evaluation_rows_with_cost=with_cost,
            evaluation_rows_cost_not_available=cost_na,
        ),
        failure_type_counts=failure_type_counts,
        recent_runs=recent_runs,
    )
