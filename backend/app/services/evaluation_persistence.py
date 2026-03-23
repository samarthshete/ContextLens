"""Persist evaluation rows and complete the run lifecycle with measured latencies."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import EvaluationResult, GenerationResult, RetrievalResult, Run
from app.services import trace_persistence as tp
from app.services.run_lifecycle import (
    STATUS_COMPLETED,
    STATUS_GENERATION_COMPLETED,
    STATUS_RETRIEVAL_COMPLETED,
)


async def persist_evaluation_and_complete_run(
    session: AsyncSession,
    *,
    run_id: int,
    evaluation_latency_ms: int,
    total_latency_ms: int,
    faithfulness: float | None = None,
    completeness: float | None = None,
    retrieval_relevance: float | None = None,
    context_coverage: float | None = None,
    groundedness: float | None = None,
    failure_type: str | None = None,
    used_llm_judge: bool = False,
    cost_usd: Decimal | None = None,
    metadata_json: dict | None = None,
    prerequisite_status: str = STATUS_RETRIEVAL_COMPLETED,
    commit: bool = False,
) -> EvaluationResult:
    """Insert ``evaluation_results`` and set run latencies + ``status=completed``.

    ``evaluation_latency_ms`` and ``total_latency_ms`` must be **measured** by the caller
    (e.g. ``time.perf_counter()``), not guessed. Non-negative integers only.

    ``prerequisite_status``:
    - ``retrieval_completed`` — heuristic path (no generation row).
    - ``generation_completed`` — LLM judge path after ``generation_results`` exist.
    """
    if evaluation_latency_ms < 0 or total_latency_ms < 0:
        raise ValueError("evaluation_latency_ms and total_latency_ms must be non-negative")

    run = await session.get(Run, run_id)
    if run is None:
        raise ValueError(f"Run id={run_id} not found")

    if run.status != prerequisite_status:
        raise ValueError(
            f"Run id={run_id} must have status {prerequisite_status!r}, got {run.status!r}"
        )

    existing = (
        await session.execute(select(EvaluationResult.id).where(EvaluationResult.run_id == run_id))
    ).scalar_one_or_none()
    if existing is not None:
        raise ValueError(f"Evaluation already exists for run id={run_id}")

    if prerequisite_status == STATUS_RETRIEVAL_COMPLETED:
        n_rr = await session.scalar(
            select(func.count()).select_from(RetrievalResult).where(RetrievalResult.run_id == run_id)
        )
        if not n_rr:
            raise ValueError(
                f"Run id={run_id} has no retrieval_results rows; refusing to mark completed"
            )

    if prerequisite_status == STATUS_GENERATION_COMPLETED:
        n_gen = await session.scalar(
            select(func.count()).select_from(GenerationResult).where(GenerationResult.run_id == run_id)
        )
        if not n_gen:
            raise ValueError(
                f"Run id={run_id} has no generation_results row; refusing LLM evaluation completion"
            )

    if used_llm_judge:
        n_gen_llm = await session.scalar(
            select(func.count()).select_from(GenerationResult).where(GenerationResult.run_id == run_id)
        )
        if not n_gen_llm:
            raise ValueError(
                f"Run id={run_id}: used_llm_judge=True but no generation_results; "
                "refusing to mark completed (full pipeline requires generation)"
            )

    er = await tp.store_evaluation_result(
        session,
        run_id=run_id,
        faithfulness=faithfulness,
        completeness=completeness,
        retrieval_relevance=retrieval_relevance,
        context_coverage=context_coverage,
        groundedness=groundedness,
        failure_type=failure_type,
        used_llm_judge=used_llm_judge,
        cost_usd=cost_usd,
        metadata_json=metadata_json,
    )

    run.evaluation_latency_ms = evaluation_latency_ms
    run.total_latency_ms = total_latency_ms
    run.status = STATUS_COMPLETED
    await session.flush()

    if commit:
        await session.commit()
        await session.refresh(er)
        await session.refresh(run)

    return er
