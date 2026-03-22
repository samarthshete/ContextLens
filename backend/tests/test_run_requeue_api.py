"""POST /api/v1/runs/{run_id}/requeue — full-run re-enqueue."""

from unittest.mock import MagicMock

import pytest
from httpx import ASGITransport, AsyncClient
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy import func, select

from app.database import async_session_maker
from app.main import app
from app.models import Chunk, Dataset, Document, EvaluationResult, PipelineConfig, QueryCase, RetrievalResult, Run
from app.services.run_lifecycle import (
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_RETRIEVAL_COMPLETED,
    STATUS_RUNNING,
)

BASE = "/api/v1"


@pytest.fixture
async def rq_client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def _minimal_registry(session):
    ds = Dataset(name="rq_ds", description="")
    session.add(ds)
    await session.flush()
    qc = QueryCase(dataset_id=ds.id, query_text="q?", expected_answer=None)
    pc = PipelineConfig(
        name="rq_pc",
        embedding_model="all-MiniLM-L6-v2",
        chunk_strategy="fixed",
        chunk_size=100,
        chunk_overlap=0,
        top_k=3,
    )
    session.add_all([qc, pc])
    await session.flush()
    return qc, pc


@pytest.mark.asyncio
async def test_requeue_success_eligible_full_run(rq_client: AsyncClient, monkeypatch):
    monkeypatch.setattr(
        "app.services.run_requeue.require_llm_api_key_for_full_mode", lambda: None
    )
    monkeypatch.setattr(
        "app.services.run_requeue.find_primary_job_for_run",
        lambda _rid: (None, None),
    )
    monkeypatch.setattr(
        "app.services.run_requeue.enqueue_full_benchmark_run",
        lambda rid, doc_id: f"requeue-job-{rid}",
    )
    monkeypatch.setattr(
        "app.services.run_requeue.get_sync_redis",
        lambda: MagicMock(exists=lambda *_a, **_k: 0),
    )

    async with async_session_maker() as session:
        qc, pc = await _minimal_registry(session)
        run = Run(query_case_id=qc.id, pipeline_config_id=pc.id, status=STATUS_RUNNING)
        session.add(run)
        await session.commit()
        rid = run.id
        count_before = (
            await session.execute(select(func.count()).select_from(Run))
        ).scalar_one()

    resp = await rq_client.post(f"{BASE}/runs/{rid}/requeue")
    assert resp.status_code == 202
    body = resp.json()
    assert body["run_id"] == rid
    assert body["status"] == STATUS_RUNNING
    assert body["job_id"] == f"requeue-job-{rid}"

    async with async_session_maker() as session:
        count_after = (await session.execute(select(func.count()).select_from(Run))).scalar_one()
    assert count_after == count_before


@pytest.mark.asyncio
async def test_requeue_404(rq_client: AsyncClient):
    resp = await rq_client.post(f"{BASE}/runs/999991/requeue")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_requeue_409_completed(rq_client: AsyncClient, monkeypatch):
    monkeypatch.setattr(
        "app.services.run_requeue.require_llm_api_key_for_full_mode", lambda: None
    )
    async with async_session_maker() as session:
        qc, pc = await _minimal_registry(session)
        run = Run(query_case_id=qc.id, pipeline_config_id=pc.id, status=STATUS_COMPLETED)
        session.add(run)
        await session.commit()
        rid = run.id

    resp = await rq_client.post(f"{BASE}/runs/{rid}/requeue")
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_requeue_409_heuristic_run(rq_client: AsyncClient, monkeypatch):
    monkeypatch.setattr(
        "app.services.run_requeue.require_llm_api_key_for_full_mode", lambda: None
    )
    async with async_session_maker() as session:
        qc, pc = await _minimal_registry(session)
        run = Run(query_case_id=qc.id, pipeline_config_id=pc.id, status=STATUS_FAILED)
        session.add(run)
        await session.flush()
        session.add(
            EvaluationResult(
                run_id=run.id,
                faithfulness=0.5,
                completeness=0.5,
                retrieval_relevance=0.5,
                context_coverage=0.5,
                failure_type="UNKNOWN",
                used_llm_judge=False,
                metadata_json={"evaluator_type": "heuristic"},
            )
        )
        await session.commit()
        rid = run.id

    resp = await rq_client.post(f"{BASE}/runs/{rid}/requeue")
    assert resp.status_code == 409
    assert "heuristic" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_requeue_409_when_lock_held(rq_client: AsyncClient, monkeypatch):
    monkeypatch.setattr(
        "app.services.run_requeue.require_llm_api_key_for_full_mode", lambda: None
    )
    monkeypatch.setattr(
        "app.services.run_requeue.find_primary_job_for_run",
        lambda _rid: (None, None),
    )
    monkeypatch.setattr(
        "app.services.run_requeue.get_sync_redis",
        lambda: MagicMock(exists=lambda *_a, **_k: 1),
    )

    async with async_session_maker() as session:
        qc, pc = await _minimal_registry(session)
        run = Run(query_case_id=qc.id, pipeline_config_id=pc.id, status=STATUS_RUNNING)
        session.add(run)
        await session.commit()
        rid = run.id

    resp = await rq_client.post(f"{BASE}/runs/{rid}/requeue")
    assert resp.status_code == 409
    assert "lock" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_requeue_409_disallowed_status_pending(rq_client: AsyncClient, monkeypatch):
    monkeypatch.setattr(
        "app.services.run_requeue.require_llm_api_key_for_full_mode", lambda: None
    )
    async with async_session_maker() as session:
        qc, pc = await _minimal_registry(session)
        run = Run(query_case_id=qc.id, pipeline_config_id=pc.id, status=STATUS_PENDING)
        session.add(run)
        await session.commit()
        rid = run.id

    resp = await rq_client.post(f"{BASE}/runs/{rid}/requeue")
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_requeue_failed_run_normalizes_to_retrieval_completed(rq_client: AsyncClient, monkeypatch):
    monkeypatch.setattr(
        "app.services.run_requeue.require_llm_api_key_for_full_mode", lambda: None
    )
    monkeypatch.setattr(
        "app.services.run_requeue.find_primary_job_for_run",
        lambda _rid: (None, None),
    )
    monkeypatch.setattr(
        "app.services.run_requeue.enqueue_full_benchmark_run",
        lambda rid, doc_id: f"job-failed-{rid}",
    )
    monkeypatch.setattr(
        "app.services.run_requeue.get_sync_redis",
        lambda: MagicMock(exists=lambda *_a, **_k: 0),
    )

    async with async_session_maker() as session:
        qc, pc = await _minimal_registry(session)
        doc = Document(
            title="rq_doc",
            source_type="txt",
            file_path="seed://requeue_fail",
            raw_text="x",
            status="processed",
        )
        session.add(doc)
        await session.flush()
        ch = Chunk(
            document_id=doc.id,
            content="hello",
            chunk_index=0,
            start_char=0,
            end_char=5,
        )
        session.add(ch)
        await session.flush()
        run = Run(query_case_id=qc.id, pipeline_config_id=pc.id, status=STATUS_FAILED)
        session.add(run)
        await session.flush()
        session.add(RetrievalResult(run_id=run.id, chunk_id=ch.id, rank=1, score=0.9))
        await session.commit()
        rid = run.id

    resp = await rq_client.post(f"{BASE}/runs/{rid}/requeue")
    assert resp.status_code == 202
    assert resp.json()["job_id"] == f"job-failed-{rid}"

    async with async_session_maker() as session:
        r2 = await session.get(Run, rid)
        assert r2 is not None
        assert r2.status == STATUS_RETRIEVAL_COMPLETED


@pytest.mark.asyncio
async def test_requeue_503_queue_unavailable(rq_client: AsyncClient, monkeypatch):
    monkeypatch.setattr(
        "app.services.run_requeue.require_llm_api_key_for_full_mode", lambda: None
    )
    monkeypatch.setattr(
        "app.services.run_requeue.find_primary_job_for_run",
        lambda _rid: (None, None),
    )
    monkeypatch.setattr(
        "app.services.run_requeue.get_sync_redis",
        lambda: MagicMock(exists=lambda *_a, **_k: 0),
    )
    def _enqueue_boom(_rid: int, _doc: int | None) -> str:
        raise RedisConnectionError("redis down")

    monkeypatch.setattr("app.services.run_requeue.enqueue_full_benchmark_run", _enqueue_boom)

    async with async_session_maker() as session:
        qc, pc = await _minimal_registry(session)
        run = Run(query_case_id=qc.id, pipeline_config_id=pc.id, status=STATUS_RUNNING)
        session.add(run)
        await session.commit()
        rid = run.id

    resp = await rq_client.post(f"{BASE}/runs/{rid}/requeue")
    assert resp.status_code == 503
