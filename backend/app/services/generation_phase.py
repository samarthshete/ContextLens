"""Persist generation for a run after retrieval (extends run lifecycle)."""

from __future__ import annotations

import time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Chunk, GenerationResult, QueryCase, RetrievalResult, Run
from app.services.rag_generation import generate_rag_answer
from app.services.run_lifecycle import STATUS_GENERATION_COMPLETED, STATUS_RETRIEVAL_COMPLETED


async def execute_generation_for_run(
    session: AsyncSession,
    *,
    run_id: int,
    commit: bool = True,
) -> GenerationResult:
    """Load retrieval chunks, call Claude, store ``generation_results``, set latencies/status.

    Expects ``run.status == retrieval_completed`` and no existing ``GenerationResult``.
    Sets ``run.generation_latency_ms`` and ``run.status = generation_completed``.
    """
    run = await session.get(Run, run_id)
    if run is None:
        raise ValueError(f"Run id={run_id} not found")
    if run.status != STATUS_RETRIEVAL_COMPLETED:
        raise ValueError(
            f"Run id={run_id} must have status {STATUS_RETRIEVAL_COMPLETED!r}, got {run.status!r}"
        )

    existing = (
        await session.execute(select(GenerationResult).where(GenerationResult.run_id == run_id))
    ).scalar_one_or_none()
    if existing is not None:
        raise ValueError(f"Generation already exists for run id={run_id}")

    stmt = (
        select(RetrievalResult, Chunk.content)
        .join(Chunk, Chunk.id == RetrievalResult.chunk_id)
        .where(RetrievalResult.run_id == run_id)
        .order_by(RetrievalResult.rank)
    )
    res = (await session.execute(stmt)).all()
    if not res:
        raise ValueError(f"No retrieval_results for run id={run_id}; cannot generate")

    qc = await session.get(QueryCase, run.query_case_id)
    if qc is None:
        raise ValueError("Query case missing")

    bodies = [content for _, content in res]

    t0 = time.perf_counter()
    gen = await generate_rag_answer(query=qc.query_text, chunk_bodies=bodies)
    gen_ms = max(0, int((time.perf_counter() - t0) * 1000))

    gr = GenerationResult(
        run_id=run_id,
        answer_text=gen.answer_text,
        model_id=gen.model_id,
        input_tokens=gen.input_tokens,
        output_tokens=gen.output_tokens,
        metadata_json=gen.metadata_json,
    )
    session.add(gr)

    run.generation_latency_ms = gen_ms
    run.status = STATUS_GENERATION_COMPLETED
    await session.flush()

    if commit:
        await session.commit()
        await session.refresh(gr)
        await session.refresh(run)

    return gr
