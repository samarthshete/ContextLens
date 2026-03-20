"""Evaluation persistence + run completion with measured latencies."""

import time
from decimal import Decimal

import pytest
from httpx import AsyncClient

from app.database import async_session_maker
from app.models import Run
from app.services import trace_persistence as tp
from app.services.benchmark_run import execute_retrieval_benchmark_run
from app.services.evaluation_persistence import persist_evaluation_and_complete_run
from app.services.run_lifecycle import STATUS_COMPLETED
from tests.conftest import make_upload

BASE = "/api/v1"

CORPUS = (
    "Evaluation metrics require stored runs. "
    "Retrieval finds relevant chunks for the query."
)


@pytest.mark.asyncio
async def test_persist_evaluation_writes_row_and_completes_run(client: AsyncClient):
    async with async_session_maker() as session:
        ds = await tp.create_dataset(session, name="eval_ds", description="")
        qc = await tp.create_query_case(
            session,
            dataset_id=ds.id,
            query_text="What requires stored runs?",
        )
        pc = await tp.create_pipeline_config(
            session,
            name="cfg-eval",
            embedding_model="all-MiniLM-L6-v2",
            chunk_strategy="fixed",
            chunk_size=120,
            chunk_overlap=0,
            top_k=5,
        )
        await session.commit()
        qid, pid = qc.id, pc.id

    up = await client.post(
        f"{BASE}/documents",
        params={"chunk_size": 80},
        files=make_upload("corpus.txt", CORPUS),
    )
    assert up.status_code == 201

    async with async_session_maker() as session:
        run = await execute_retrieval_benchmark_run(
            session,
            query_case_id=qid,
            pipeline_config_id=pid,
            commit=True,
        )
        run_id = run.id
        retrieval_ms = run.retrieval_latency_ms
        assert retrieval_ms is not None

    t0 = time.perf_counter()
    time.sleep(0.002)
    eval_ms = max(1, int((time.perf_counter() - t0) * 1000))
    total_ms = retrieval_ms + eval_ms

    async with async_session_maker() as session:
        er = await persist_evaluation_and_complete_run(
            session,
            run_id=run_id,
            evaluation_latency_ms=eval_ms,
            total_latency_ms=total_ms,
            faithfulness=0.85,
            completeness=0.8,
            retrieval_relevance=0.9,
            context_coverage=0.75,
            failure_type="NO_FAILURE",
            used_llm_judge=False,
            cost_usd=Decimal("0.001234"),
            metadata_json={"source": "pytest"},
            commit=True,
        )

    assert er.faithfulness == pytest.approx(0.85)
    assert er.metadata_json == {"source": "pytest"}

    async with async_session_maker() as session:
        r = await session.get(Run, run_id)
        assert r is not None
        assert r.status == STATUS_COMPLETED
        assert r.evaluation_latency_ms == eval_ms
        assert r.total_latency_ms == total_ms
