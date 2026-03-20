"""Benchmark trace persistence + retrieval-only run (uses real DB + embedder)."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select, func

from app.database import async_session_maker
from app.models import RetrievalResult, Run
from app.services import trace_persistence as tp
from app.services.benchmark_run import execute_retrieval_benchmark_run
from app.services.run_lifecycle import STATUS_RETRIEVAL_COMPLETED
from tests.conftest import make_upload

BASE = "/api/v1"

SAMPLE = (
    "Retrieval-Augmented Generation combines retrieval with language model generation. "
    "Dense vector similarity finds relevant passages."
)


@pytest.mark.asyncio
async def test_execute_retrieval_benchmark_persists_run_and_results(client: AsyncClient):
    async with async_session_maker() as session:
        ds = await tp.create_dataset(session, name="bench_ds", description="test dataset")
        qc = await tp.create_query_case(
            session,
            dataset_id=ds.id,
            query_text="What is dense vector retrieval?",
        )
        pc = await tp.create_pipeline_config(
            session,
            name="default",
            embedding_model="all-MiniLM-L6-v2",
            chunk_strategy="fixed",
            chunk_size=200,
            chunk_overlap=0,
            top_k=5,
        )
        await session.commit()
        qid, pid = qc.id, pc.id

    up = await client.post(
        f"{BASE}/documents",
        params={"chunk_size": 120},
        files=make_upload("corpus.txt", SAMPLE),
    )
    assert up.status_code == 201

    async with async_session_maker() as session:
        run = await execute_retrieval_benchmark_run(
            session,
            query_case_id=qid,
            pipeline_config_id=pid,
            commit=True,
        )
        assert run.id is not None
        assert run.status == STATUS_RETRIEVAL_COMPLETED
        assert run.retrieval_latency_ms is not None
        assert run.retrieval_latency_ms >= 0

    async with async_session_maker() as session:
        n_rr = (
            await session.execute(
                select(func.count()).select_from(RetrievalResult).where(RetrievalResult.run_id == run.id)
            )
        ).scalar_one()
        assert n_rr > 0

        r = await session.get(Run, run.id)
        assert r is not None
        assert r.retrieval_latency_ms is not None
