"""``get_phase_latency_distribution`` — PostgreSQL percentile aggregates on ``runs``."""

import pytest

from app.database import async_session_maker
from app.models import Dataset, PipelineConfig, QueryCase, Run
from app.services.phase_latency_distribution import get_phase_latency_distribution


async def _run_with_total_ms(session, *, total_ms: int | None) -> None:
    ds = Dataset(name="pld_tot_ds", description="")
    session.add(ds)
    await session.flush()
    qc = QueryCase(dataset_id=ds.id, query_text="q", expected_answer=None)
    pc = PipelineConfig(
        name="pld_tot_pc",
        embedding_model="m",
        chunk_strategy="fixed",
        chunk_size=64,
        chunk_overlap=0,
        top_k=3,
    )
    session.add_all([qc, pc])
    await session.flush()
    session.add(
        Run(
            query_case_id=qc.id,
            pipeline_config_id=pc.id,
            status="completed",
            retrieval_latency_ms=1,
            generation_latency_ms=None,
            evaluation_latency_ms=None,
            total_latency_ms=total_ms,
        )
    )
    await session.commit()


async def _minimal_run(session, *, retrieval_ms: int | None) -> None:
    ds = Dataset(name="pld_ds", description="")
    session.add(ds)
    await session.flush()
    qc = QueryCase(dataset_id=ds.id, query_text="q", expected_answer=None)
    pc = PipelineConfig(
        name="pld_pc",
        embedding_model="m",
        chunk_strategy="fixed",
        chunk_size=64,
        chunk_overlap=0,
        top_k=3,
    )
    session.add_all([qc, pc])
    await session.flush()
    session.add(
        Run(
            query_case_id=qc.id,
            pipeline_config_id=pc.id,
            status="completed",
            retrieval_latency_ms=retrieval_ms,
            generation_latency_ms=None,
            evaluation_latency_ms=None,
            total_latency_ms=retrieval_ms,
        )
    )
    await session.commit()


@pytest.mark.asyncio
async def test_retrieval_percentiles_match_postgresql_contiguous():
    """Five known latencies — median and p95 are computed, not guessed."""
    async with async_session_maker() as session:
        for ms in (10, 20, 30, 40, 100):
            await _minimal_run(session, retrieval_ms=ms)

    async with async_session_maker() as session:
        dist = await get_phase_latency_distribution(session, Run.retrieval_latency_ms)

    assert dist.count == 5
    assert dist.min_ms == 10.0
    assert dist.max_ms == 100.0
    assert dist.avg_ms == pytest.approx(40.0)
    assert dist.median_ms == pytest.approx(30.0)
    assert dist.p95_ms is not None
    assert dist.p95_ms >= 40.0


@pytest.mark.asyncio
async def test_total_latency_percentiles_same_engine_as_retrieval():
    """``runs.total_latency_ms`` uses the same aggregate query path as other phases."""
    async with async_session_maker() as session:
        for ms in (1000, 2000, 3000, 4000, 10000):
            await _run_with_total_ms(session, total_ms=ms)

    async with async_session_maker() as session:
        dist = await get_phase_latency_distribution(session, Run.total_latency_ms)

    assert dist.count == 5
    assert dist.avg_ms == pytest.approx(4000.0)
    assert dist.median_ms == pytest.approx(3000.0)
    assert dist.p95_ms is not None
    # Sec metrics in API are ``dist.avg_ms / 1000`` and ``dist.p95_ms / 1000``
    assert dist.avg_ms / 1000.0 == pytest.approx(4.0)
    assert dist.p95_ms / 1000.0 >= 4.0


@pytest.mark.asyncio
async def test_empty_distribution_when_all_null():
    async with async_session_maker() as session:
        await _minimal_run(session, retrieval_ms=None)

    async with async_session_maker() as session:
        dist = await get_phase_latency_distribution(session, Run.retrieval_latency_ms)

    assert dist.count == 0
    assert dist.median_ms is None
    assert dist.p95_ms is None
    assert dist.avg_ms is None
