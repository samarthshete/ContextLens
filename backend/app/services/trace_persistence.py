"""Create benchmark/trace rows. Callers own ``commit`` unless using ``benchmark_run`` entrypoint."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Dataset,
    EvaluationResult,
    PipelineConfig,
    QueryCase,
    RetrievalResult,
    Run,
)


async def create_dataset(
    session: AsyncSession,
    *,
    name: str,
    description: str | None = None,
    metadata_json: dict | None = None,
) -> Dataset:
    d = Dataset(name=name, description=description, metadata_json=metadata_json)
    session.add(d)
    await session.flush()
    return d


async def create_query_case(
    session: AsyncSession,
    *,
    dataset_id: int,
    query_text: str,
    expected_answer: str | None = None,
    metadata_json: dict | None = None,
) -> QueryCase:
    qc = QueryCase(
        dataset_id=dataset_id,
        query_text=query_text,
        expected_answer=expected_answer,
        metadata_json=metadata_json,
    )
    session.add(qc)
    await session.flush()
    return qc


async def create_pipeline_config(
    session: AsyncSession,
    *,
    name: str,
    embedding_model: str,
    chunk_strategy: str,
    chunk_size: int,
    chunk_overlap: int,
    top_k: int,
    metadata_json: dict | None = None,
) -> PipelineConfig:
    pc = PipelineConfig(
        name=name,
        embedding_model=embedding_model,
        chunk_strategy=chunk_strategy,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        top_k=top_k,
        metadata_json=metadata_json,
    )
    session.add(pc)
    await session.flush()
    return pc


async def create_run(
    session: AsyncSession,
    *,
    query_case_id: int,
    pipeline_config_id: int,
    status: str = "pending",
) -> Run:
    r = Run(
        query_case_id=query_case_id,
        pipeline_config_id=pipeline_config_id,
        status=status,
    )
    session.add(r)
    await session.flush()
    return r


async def store_retrieval_results(
    session: AsyncSession,
    *,
    run_id: int,
    chunk_scores: list[tuple[int, int, float]],
) -> None:
    """Store retrieval rows. Each tuple is ``(chunk_id, rank, score)``; ``rank`` is 1-based."""
    for chunk_id, rank, score in chunk_scores:
        session.add(
            RetrievalResult(
                run_id=run_id,
                chunk_id=chunk_id,
                rank=rank,
                score=score,
            )
        )
    await session.flush()


async def store_evaluation_result(
    session: AsyncSession,
    *,
    run_id: int,
    faithfulness: float | None = None,
    completeness: float | None = None,
    retrieval_relevance: float | None = None,
    context_coverage: float | None = None,
    groundedness: float | None = None,
    failure_type: str | None = None,
    used_llm_judge: bool = False,
    cost_usd: Decimal | None = None,
    metadata_json: dict | None = None,
) -> EvaluationResult:
    er = EvaluationResult(
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
    session.add(er)
    await session.flush()
    return er
