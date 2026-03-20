"""Execute a minimal benchmark step using the live retrieval pipeline and persist a run."""

from __future__ import annotations

import time

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PipelineConfig, QueryCase, Run
from app.services import trace_persistence as tp
from app.services.retrieval import search_chunks
from app.services.run_lifecycle import STATUS_RETRIEVAL_COMPLETED, STATUS_RUNNING


async def execute_retrieval_benchmark_run(
    db: AsyncSession,
    *,
    query_case_id: int,
    pipeline_config_id: int,
    document_id: int | None = None,
    commit: bool = True,
) -> Run:
    """Run ``search_chunks`` for the query case text, persist ``retrieval_results``, set latency.

    Uses ``pipeline_config.top_k`` and optional ``document_id`` filter (same semantics as API search).

    When ``commit`` is True, commits the transaction and refreshes ``run``.
    """
    qc = await db.get(QueryCase, query_case_id)
    if qc is None:
        raise ValueError(f"QueryCase id={query_case_id} not found")
    pc = await db.get(PipelineConfig, pipeline_config_id)
    if pc is None:
        raise ValueError(f"PipelineConfig id={pipeline_config_id} not found")

    run = await tp.create_run(
        db,
        query_case_id=query_case_id,
        pipeline_config_id=pipeline_config_id,
        status=STATUS_RUNNING,
    )
    await db.flush()
    # Persist ``running`` before retrieval so list/detail can observe lifecycle mid-flight.
    if commit:
        await db.commit()
        await db.refresh(run)

    t0 = time.perf_counter()
    hits = await search_chunks(
        qc.query_text,
        db,
        top_k=pc.top_k,
        document_id=document_id,
    )
    elapsed_ms = int((time.perf_counter() - t0) * 1000)

    rows = [(h["chunk_id"], i + 1, float(h["score"])) for i, h in enumerate(hits)]
    await tp.store_retrieval_results(db, run_id=run.id, chunk_scores=rows)

    run.retrieval_latency_ms = elapsed_ms
    run.status = STATUS_RETRIEVAL_COMPLETED
    await db.flush()

    if commit:
        await db.commit()
        await db.refresh(run)
    return run


async def execute_retrieval_for_existing_run(
    db: AsyncSession,
    *,
    run_id: int,
    document_id: int | None = None,
    commit: bool = True,
) -> Run:
    """Vector search + persist retrieval rows for a run already created (``status`` typically ``running``).

    Used when the HTTP layer returns early (202) and continues the pipeline in a background task.
    Sets ``retrieval_completed`` and ``retrieval_latency_ms``.
    """
    run = await db.get(Run, run_id)
    if run is None:
        raise ValueError(f"Run id={run_id} not found")
    qc = await db.get(QueryCase, run.query_case_id)
    pc = await db.get(PipelineConfig, run.pipeline_config_id)
    if qc is None or pc is None:
        raise ValueError("Query case or pipeline config missing for run")

    t0 = time.perf_counter()
    hits = await search_chunks(
        qc.query_text,
        db,
        top_k=pc.top_k,
        document_id=document_id,
    )
    elapsed_ms = int((time.perf_counter() - t0) * 1000)

    rows = [(h["chunk_id"], i + 1, float(h["score"])) for i, h in enumerate(hits)]
    await tp.store_retrieval_results(db, run_id=run.id, chunk_scores=rows)

    run.retrieval_latency_ms = elapsed_ms
    run.status = STATUS_RETRIEVAL_COMPLETED
    await db.flush()

    if commit:
        await db.commit()
        await db.refresh(run)
    return run
