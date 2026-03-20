"""Load a full run trace for inspection (API + demos)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.evaluator_bucket import resolved_evaluator_type
from app.models import Chunk, EvaluationResult, GenerationResult, PipelineConfig, QueryCase, RetrievalResult, Run
from app.schemas.run_detail import (
    EvaluationOut,
    GenerationOut,
    PipelineConfigBrief,
    QueryCaseBrief,
    RetrievalHitOut,
    RunDetailResponse,
)


async def get_run_detail(session: AsyncSession, run_id: int) -> RunDetailResponse | None:
    """Return structured run detail or ``None`` if the run does not exist."""
    run = await session.get(Run, run_id)
    if run is None:
        return None

    qc = await session.get(QueryCase, run.query_case_id)
    pc = await session.get(PipelineConfig, run.pipeline_config_id)
    if qc is None or pc is None:
        return None

    stmt = (
        select(RetrievalResult, Chunk)
        .join(Chunk, Chunk.id == RetrievalResult.chunk_id)
        .where(RetrievalResult.run_id == run_id)
        .order_by(RetrievalResult.rank)
    )
    rows = (await session.execute(stmt)).all()
    hits = [
        RetrievalHitOut(
            rank=rr.rank,
            score=float(rr.score),
            chunk_id=chunk.id,
            document_id=chunk.document_id,
            content=chunk.content,
            chunk_index=chunk.chunk_index,
        )
        for rr, chunk in rows
    ]

    gen_row = (
        await session.execute(select(GenerationResult).where(GenerationResult.run_id == run_id))
    ).scalar_one_or_none()
    generation: GenerationOut | None = None
    if gen_row is not None:
        generation = GenerationOut(
            answer_text=gen_row.answer_text,
            model_id=gen_row.model_id,
            input_tokens=gen_row.input_tokens,
            output_tokens=gen_row.output_tokens,
            metadata_json=gen_row.metadata_json,
        )

    ev_row = (
        await session.execute(select(EvaluationResult).where(EvaluationResult.run_id == run_id))
    ).scalar_one_or_none()
    evaluation: EvaluationOut | None = None
    evaluator_type = "heuristic"
    if ev_row is not None:
        evaluator_type = resolved_evaluator_type(
            used_llm_judge=ev_row.used_llm_judge,
            metadata_json=ev_row.metadata_json,
        )
        evaluation = EvaluationOut(
            faithfulness=ev_row.faithfulness,
            completeness=ev_row.completeness,
            retrieval_relevance=ev_row.retrieval_relevance,
            context_coverage=ev_row.context_coverage,
            groundedness=ev_row.groundedness,
            failure_type=ev_row.failure_type,
            used_llm_judge=ev_row.used_llm_judge,
            cost_usd=ev_row.cost_usd,
            metadata_json=ev_row.metadata_json,
        )
    else:
        evaluator_type = "none"

    return RunDetailResponse(
        run_id=run.id,
        status=run.status,
        created_at=run.created_at,
        retrieval_latency_ms=run.retrieval_latency_ms,
        generation_latency_ms=run.generation_latency_ms,
        evaluation_latency_ms=run.evaluation_latency_ms,
        total_latency_ms=run.total_latency_ms,
        evaluator_type=evaluator_type,
        query_case=QueryCaseBrief.model_validate(qc),
        pipeline_config=PipelineConfigBrief.model_validate(pc),
        retrieval_hits=hits,
        generation=generation,
        evaluation=evaluation,
    )
