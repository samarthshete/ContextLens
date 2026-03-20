"""LLM judge evaluation after generation (completes run)."""

from __future__ import annotations

import time
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Chunk, GenerationResult, QueryCase, RetrievalResult, Run
from app.services.cost_estimation import estimate_usd_from_tokens
from app.services.evaluation_persistence import persist_evaluation_and_complete_run
from app.services.llm_judge_evaluation import evaluate_with_llm_judge
from app.services.run_lifecycle import STATUS_GENERATION_COMPLETED


async def execute_llm_judge_and_complete_run(
    session: AsyncSession,
    *,
    run_id: int,
    commit: bool = True,
) -> None:
    """Run Claude judge on stored generation + context; persist evaluation + ``completed``.

    Expects ``status == generation_completed`` and no ``evaluation_results`` row yet.
    ``total_latency_ms`` = sum of measured retrieval + generation + evaluation phase ms on the run.
    ``cost_usd`` = estimated generation + judge tokens when pricing config is non-zero.
    """
    run = await session.get(Run, run_id)
    if run is None:
        raise ValueError(f"Run id={run_id} not found")
    if run.status != STATUS_GENERATION_COMPLETED:
        raise ValueError(
            f"Run id={run_id} must have status {STATUS_GENERATION_COMPLETED!r}, got {run.status!r}"
        )

    gen = (
        await session.execute(select(GenerationResult).where(GenerationResult.run_id == run_id))
    ).scalar_one_or_none()
    if gen is None:
        raise ValueError(f"No generation_results for run id={run_id}")

    qc = await session.get(QueryCase, run.query_case_id)
    if qc is None:
        raise ValueError("Query case missing")

    stmt = (
        select(RetrievalResult, Chunk.content)
        .join(Chunk, Chunk.id == RetrievalResult.chunk_id)
        .where(RetrievalResult.run_id == run_id)
        .order_by(RetrievalResult.rank)
    )
    rows = (await session.execute(stmt)).all()
    bodies = [content for _, content in rows]

    t0 = time.perf_counter()
    ev = await evaluate_with_llm_judge(
        query=qc.query_text,
        context_chunks=bodies,
        generated_answer=gen.answer_text,
        reference_answer=qc.expected_answer,
    )
    eval_ms = max(0, int((time.perf_counter() - t0) * 1000))

    retrieval_ms = run.retrieval_latency_ms or 0
    generation_ms = run.generation_latency_ms or 0
    total_ms = retrieval_ms + generation_ms + eval_ms

    gen_cost = estimate_usd_from_tokens(gen.input_tokens, gen.output_tokens)
    judge_cost = estimate_usd_from_tokens(ev.judge_input_tokens, ev.judge_output_tokens)
    cost_usd: Decimal | None = None
    if gen_cost is not None or judge_cost is not None:
        cost_usd = (gen_cost or Decimal("0")) + (judge_cost or Decimal("0"))
        if cost_usd == 0:
            cost_usd = None

    meta = dict(ev.metadata_json)
    meta["generation_model"] = gen.model_id
    meta["generation_input_tokens"] = gen.input_tokens
    meta["generation_output_tokens"] = gen.output_tokens

    await persist_evaluation_and_complete_run(
        session,
        run_id=run_id,
        evaluation_latency_ms=eval_ms,
        total_latency_ms=total_ms,
        faithfulness=ev.faithfulness,
        completeness=ev.completeness,
        retrieval_relevance=ev.retrieval_relevance,
        context_coverage=ev.context_coverage,
        groundedness=ev.groundedness,
        failure_type=ev.failure_type,
        used_llm_judge=True,
        cost_usd=cost_usd,
        metadata_json=meta,
        prerequisite_status=STATUS_GENERATION_COMPLETED,
        commit=commit,
    )
