"""GET /api/v1/runs/{run_id}/queue-status — queue / lock inspection."""

from unittest.mock import MagicMock

import pytest
from httpx import ASGITransport, AsyncClient
from redis.exceptions import ConnectionError as RedisConnectionError

from app.database import async_session_maker
from app.main import app
from app.models import Dataset, EvaluationResult, PipelineConfig, QueryCase, Run
from app.services.run_lifecycle import (
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_RUNNING,
)

BASE = "/api/v1"


@pytest.fixture
async def qs_client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def _minimal_registry(session):
    ds = Dataset(name="qs_ds", description="")
    session.add(ds)
    await session.flush()
    qc = QueryCase(dataset_id=ds.id, query_text="q?", expected_answer=None)
    pc = PipelineConfig(
        name="qs_pc",
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
async def test_queue_status_full_run_with_job(qs_client: AsyncClient, monkeypatch):
    monkeypatch.setattr(
        "app.services.run_queue_status.find_primary_job_for_run",
        lambda rid: ("job-abc", "queued"),
    )
    monkeypatch.setattr(
        "app.services.run_queue_status.get_sync_redis",
        lambda: MagicMock(exists=lambda *_a, **_k: 0),
    )

    async with async_session_maker() as session:
        qc, pc = await _minimal_registry(session)
        run = Run(query_case_id=qc.id, pipeline_config_id=pc.id, status=STATUS_RUNNING)
        session.add(run)
        await session.commit()
        rid = run.id

    resp = await qs_client.get(f"{BASE}/runs/{rid}/queue-status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["run_id"] == rid
    assert body["run_status"] == STATUS_RUNNING
    assert body["pipeline"] == "full"
    assert body["job_id"] == "job-abc"
    assert body["rq_job_status"] == "queued"
    assert body["lock_present"] is False
    assert body["requeue_eligible"] is True
    assert body.get("detail") is None


@pytest.mark.asyncio
async def test_queue_status_404(qs_client: AsyncClient):
    resp = await qs_client.get(f"{BASE}/runs/999992/queue-status")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_queue_status_heuristic_run(qs_client: AsyncClient, monkeypatch):
    """Heuristic runs skip Redis; ineligible with explanatory detail."""
    boom = MagicMock(side_effect=AssertionError("Redis should not be touched"))
    monkeypatch.setattr("app.services.run_queue_status.get_sync_redis", boom)

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

    resp = await qs_client.get(f"{BASE}/runs/{rid}/queue-status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["pipeline"] == "heuristic"
    assert body["job_id"] is None
    assert body["rq_job_status"] is None
    assert body["lock_present"] is False
    assert body["requeue_eligible"] is False
    assert "heuristic" in (body.get("detail") or "").lower()


@pytest.mark.asyncio
async def test_queue_status_redis_unavailable_503(qs_client: AsyncClient, monkeypatch):
    monkeypatch.setattr(
        "app.services.run_queue_status.find_primary_job_for_run",
        lambda _rid: (None, None),
    )
    monkeypatch.setattr(
        "app.services.run_queue_status.get_sync_redis",
        lambda: MagicMock(exists=lambda *_a, **_k: (_ for _ in ()).throw(RedisConnectionError("down"))),
    )

    async with async_session_maker() as session:
        qc, pc = await _minimal_registry(session)
        run = Run(query_case_id=qc.id, pipeline_config_id=pc.id, status=STATUS_RUNNING)
        session.add(run)
        await session.commit()
        rid = run.id

    resp = await qs_client.get(f"{BASE}/runs/{rid}/queue-status")
    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_queue_status_lock_present_not_eligible(qs_client: AsyncClient, monkeypatch):
    monkeypatch.setattr(
        "app.services.run_queue_status.find_primary_job_for_run",
        lambda _rid: (None, None),
    )
    monkeypatch.setattr(
        "app.services.run_queue_status.get_sync_redis",
        lambda: MagicMock(exists=lambda *_a, **_k: 1),
    )

    async with async_session_maker() as session:
        qc, pc = await _minimal_registry(session)
        run = Run(query_case_id=qc.id, pipeline_config_id=pc.id, status=STATUS_RUNNING)
        session.add(run)
        await session.commit()
        rid = run.id

    resp = await qs_client.get(f"{BASE}/runs/{rid}/queue-status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["lock_present"] is True
    assert body["requeue_eligible"] is False
    assert body["detail"] and "lock" in body["detail"].lower()


@pytest.mark.asyncio
async def test_queue_status_matches_requeue_structural_and_lock(qs_client: AsyncClient, monkeypatch):
    """When structural OK and no lock, GET agrees POST would pass structural+lock (API key aside)."""
    monkeypatch.setattr("app.services.run_requeue.require_llm_api_key_for_full_mode", lambda: None)
    monkeypatch.setattr(
        "app.services.run_requeue.enqueue_full_benchmark_run",
        lambda rid, doc_id: f"rej-{rid}",
    )
    monkeypatch.setattr(
        "app.services.run_queue_status.find_primary_job_for_run",
        lambda _rid: ("seen", "started"),
    )
    monkeypatch.setattr(
        "app.services.run_requeue.find_primary_job_for_run",
        lambda _rid: ("seen", "started"),
    )
    redis_m = MagicMock(exists=lambda *_a, **_k: 0)
    monkeypatch.setattr("app.services.run_queue_status.get_sync_redis", lambda: redis_m)
    monkeypatch.setattr("app.services.run_requeue.get_sync_redis", lambda: redis_m)

    async with async_session_maker() as session:
        qc, pc = await _minimal_registry(session)
        run = Run(query_case_id=qc.id, pipeline_config_id=pc.id, status=STATUS_RUNNING)
        session.add(run)
        await session.commit()
        rid = run.id

    st = await qs_client.get(f"{BASE}/runs/{rid}/queue-status")
    assert st.status_code == 200
    assert st.json()["requeue_eligible"] is True

    rq = await qs_client.post(f"{BASE}/runs/{rid}/requeue")
    assert rq.status_code == 202


@pytest.mark.asyncio
async def test_queue_status_completed_not_eligible(qs_client: AsyncClient, monkeypatch):
    monkeypatch.setattr(
        "app.services.run_queue_status.find_primary_job_for_run",
        lambda _rid: (None, None),
    )
    monkeypatch.setattr(
        "app.services.run_queue_status.get_sync_redis",
        lambda: MagicMock(exists=lambda *_a, **_k: 0),
    )

    async with async_session_maker() as session:
        qc, pc = await _minimal_registry(session)
        run = Run(query_case_id=qc.id, pipeline_config_id=pc.id, status=STATUS_COMPLETED)
        session.add(run)
        await session.commit()
        rid = run.id

    resp = await qs_client.get(f"{BASE}/runs/{rid}/queue-status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["pipeline"] == "full"
    assert body["requeue_eligible"] is False
    assert "completed" in (body.get("detail") or "").lower()


@pytest.mark.asyncio
async def test_queue_status_disallowed_status_pending(qs_client: AsyncClient, monkeypatch):
    monkeypatch.setattr(
        "app.services.run_queue_status.find_primary_job_for_run",
        lambda _rid: (None, None),
    )
    monkeypatch.setattr(
        "app.services.run_queue_status.get_sync_redis",
        lambda: MagicMock(exists=lambda *_a, **_k: 0),
    )

    async with async_session_maker() as session:
        qc, pc = await _minimal_registry(session)
        run = Run(query_case_id=qc.id, pipeline_config_id=pc.id, status=STATUS_PENDING)
        session.add(run)
        await session.commit()
        rid = run.id

    resp = await qs_client.get(f"{BASE}/runs/{rid}/queue-status")
    assert resp.status_code == 200
    assert resp.json()["requeue_eligible"] is False
