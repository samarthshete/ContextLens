"""Interrupted full-run recovery: RQ failure callback + stale Redis lock."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.database import async_session_maker
from app.main import app
from app.models import Dataset, PipelineConfig, QueryCase, Run
from app.services.run_create import mark_run_failed_sync
from app.services.run_lifecycle import STATUS_FAILED, STATUS_RUNNING

BASE = "/api/v1"


@pytest.fixture
async def fl_client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def _minimal_registry(session):
    ds = Dataset(name="fl_ds", description="")
    session.add(ds)
    await session.flush()
    qc = QueryCase(dataset_id=ds.id, query_text="q?", expected_answer=None)
    pc = PipelineConfig(
        name="fl_pc",
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
async def test_mark_run_failed_sync_from_async_test_session():
    """Sync psycopg path works while pytest-asyncio has a running loop."""
    async with async_session_maker() as session:
        qc, pc = await _minimal_registry(session)
        run = Run(query_case_id=qc.id, pipeline_config_id=pc.id, status=STATUS_RUNNING)
        session.add(run)
        await session.commit()
        rid = run.id

    mark_run_failed_sync(rid)

    async with async_session_maker() as session:
        r2 = await session.get(Run, rid)
        assert r2 is not None
        assert r2.status == STATUS_FAILED


class _ToggleLockRedis:
    """exists=1 until delete() is called (stale worker lock)."""

    def __init__(self) -> None:
        self.held = True

    def exists(self, *_a, **_k):
        return 1 if self.held else 0

    def delete(self, *_a, **_k):
        self.held = False


@pytest.mark.asyncio
async def test_queue_status_clears_stale_lock_when_rq_job_failed(fl_client: AsyncClient, monkeypatch):
    redis = _ToggleLockRedis()
    monkeypatch.setattr("app.services.run_queue_status.get_sync_redis", lambda: redis)
    monkeypatch.setattr("app.workers.full_run_worker.get_sync_redis", lambda: redis)
    monkeypatch.setattr(
        "app.services.run_queue_status.find_primary_job_for_run",
        lambda _rid: ("job-dead", "failed"),
    )

    async with async_session_maker() as session:
        qc, pc = await _minimal_registry(session)
        run = Run(query_case_id=qc.id, pipeline_config_id=pc.id, status=STATUS_RUNNING)
        session.add(run)
        await session.commit()
        rid = run.id

    resp = await fl_client.get(f"{BASE}/runs/{rid}/queue-status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["lock_present"] is False
    assert body["requeue_eligible"] is True
    assert body["rq_job_status"] == "failed"


@pytest.mark.asyncio
async def test_requeue_succeeds_after_stale_lock_when_rq_job_failed(fl_client: AsyncClient, monkeypatch):
    monkeypatch.setattr(
        "app.services.run_requeue.require_llm_api_key_for_full_mode", lambda: None
    )
    monkeypatch.setattr(
        "app.services.run_requeue.enqueue_full_benchmark_run",
        lambda rid, doc_id: f"recovery-{rid}",
    )
    redis = _ToggleLockRedis()
    monkeypatch.setattr("app.services.run_requeue.get_sync_redis", lambda: redis)
    monkeypatch.setattr("app.workers.full_run_worker.get_sync_redis", lambda: redis)
    monkeypatch.setattr(
        "app.services.run_requeue.find_primary_job_for_run",
        lambda _rid: ("job-dead", "failed"),
    )

    async with async_session_maker() as session:
        qc, pc = await _minimal_registry(session)
        run = Run(query_case_id=qc.id, pipeline_config_id=pc.id, status=STATUS_RUNNING)
        session.add(run)
        await session.commit()
        rid = run.id

    resp = await fl_client.post(f"{BASE}/runs/{rid}/requeue")
    assert resp.status_code == 202
    assert resp.json()["job_id"] == f"recovery-{rid}"


@pytest.mark.asyncio
async def test_mark_run_failed_sync_idempotent_second_call_no_op():
    """Second sync mark is safe (already ``failed``)."""
    async with async_session_maker() as session:
        qc, pc = await _minimal_registry(session)
        run = Run(query_case_id=qc.id, pipeline_config_id=pc.id, status=STATUS_RUNNING)
        session.add(run)
        await session.commit()
        rid = run.id

    mark_run_failed_sync(rid)
    mark_run_failed_sync(rid)

    async with async_session_maker() as session:
        r2 = await session.get(Run, rid)
        assert r2 is not None
        assert r2.status == STATUS_FAILED
