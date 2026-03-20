"""List runs with filters and pagination (no raw SQL for callers)."""

from __future__ import annotations

from typing import Literal

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from app.domain.evaluator_bucket import resolved_evaluator_type, sql_is_heuristic_bucket, sql_is_llm_bucket
from app.models import EvaluationResult, QueryCase, Run
from app.schemas.run_list import RunListItem


def _base_select() -> Select:
    return (
        select(Run, EvaluationResult, QueryCase)
        .join(QueryCase, Run.query_case_id == QueryCase.id)
    )


async def count_runs(
    session: AsyncSession,
    *,
    dataset_id: int | None,
    pipeline_config_id: int | None,
    evaluator_type: Literal["heuristic", "llm"] | None,
    status: str | None,
) -> int:
    stmt = select(func.count()).select_from(Run).join(QueryCase, Run.query_case_id == QueryCase.id)
    if dataset_id is not None:
        stmt = stmt.where(QueryCase.dataset_id == dataset_id)
    if pipeline_config_id is not None:
        stmt = stmt.where(Run.pipeline_config_id == pipeline_config_id)
    if status is not None:
        stmt = stmt.where(Run.status == status)
    if evaluator_type == "llm":
        stmt = stmt.join(EvaluationResult, EvaluationResult.run_id == Run.id).where(
            text(sql_is_llm_bucket("evaluation_results"))
        )
    elif evaluator_type == "heuristic":
        stmt = stmt.join(EvaluationResult, EvaluationResult.run_id == Run.id).where(
            text(sql_is_heuristic_bucket("evaluation_results"))
        )
    q = await session.execute(stmt)
    return int(q.scalar_one())


async def list_runs(
    session: AsyncSession,
    *,
    dataset_id: int | None = None,
    pipeline_config_id: int | None = None,
    evaluator_type: Literal["heuristic", "llm"] | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[RunListItem], int]:
    total = await count_runs(
        session,
        dataset_id=dataset_id,
        pipeline_config_id=pipeline_config_id,
        evaluator_type=evaluator_type,
        status=status,
    )

    if evaluator_type in ("llm", "heuristic"):
        stmt = _base_select().join(EvaluationResult, EvaluationResult.run_id == Run.id)
        if evaluator_type == "llm":
            stmt = stmt.where(text(sql_is_llm_bucket("evaluation_results")))
        else:
            stmt = stmt.where(text(sql_is_heuristic_bucket("evaluation_results")))
    else:
        stmt = _base_select().outerjoin(EvaluationResult, EvaluationResult.run_id == Run.id)

    if dataset_id is not None:
        stmt = stmt.where(QueryCase.dataset_id == dataset_id)
    if pipeline_config_id is not None:
        stmt = stmt.where(Run.pipeline_config_id == pipeline_config_id)
    if status is not None:
        stmt = stmt.where(Run.status == status)

    stmt = stmt.order_by(Run.created_at.desc(), Run.id.desc()).limit(limit).offset(offset)

    result = await session.execute(stmt)
    rows = result.all()

    items: list[RunListItem] = []
    for run, ev, qc in rows:
        ev_type: Literal["heuristic", "llm", "none"] = "none"
        has_ev = ev is not None
        if has_ev:
            ev_type = resolved_evaluator_type(
                used_llm_judge=bool(ev.used_llm_judge),
                metadata_json=ev.metadata_json,
            )  # type: ignore[assignment]
        items.append(
            RunListItem(
                run_id=run.id,
                status=run.status,
                created_at=run.created_at,
                dataset_id=qc.dataset_id,
                query_case_id=run.query_case_id,
                pipeline_config_id=run.pipeline_config_id,
                query_text=qc.query_text,
                retrieval_latency_ms=run.retrieval_latency_ms,
                generation_latency_ms=run.generation_latency_ms,
                evaluation_latency_ms=run.evaluation_latency_ms,
                total_latency_ms=run.total_latency_ms,
                evaluator_type=ev_type,
                has_evaluation=has_ev,
            )
        )

    return items, total
