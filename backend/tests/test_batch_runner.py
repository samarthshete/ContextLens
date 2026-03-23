"""Batch benchmark runner (empty grid — no query cases)."""

import uuid

import pytest

from app.database import async_session_maker
from app.models import Dataset, PipelineConfig
from app.services.batch_runner import run_batch_benchmark


@pytest.mark.asyncio
async def test_run_batch_benchmark_zero_cells_when_no_queries():
    async with async_session_maker() as session:
        ds = Dataset(name=f"batch_empty_ds_{uuid.uuid4().hex[:10]}", description="")
        pc = PipelineConfig(
            name=f"batch_pc_{uuid.uuid4().hex[:10]}",
            embedding_model="all-MiniLM-L6-v2",
            chunk_strategy="fixed",
            chunk_size=50,
            chunk_overlap=0,
            top_k=2,
        )
        session.add_all([ds, pc])
        await session.flush()
        ds_id, pc_id = ds.id, pc.id
        await session.commit()

    async with async_session_maker() as session:
        result = await run_batch_benchmark(
            session,
            [ds_id],
            [pc_id],
            queries_per_dataset=3,
            runs_per_query=2,
            evaluator_type="heuristic",
            commit=True,
        )

    assert result.total_runs == 0
    assert result.successes == 0
    assert result.failures == 0
    assert result.success_rate == 0.0
    assert result.batch_id
