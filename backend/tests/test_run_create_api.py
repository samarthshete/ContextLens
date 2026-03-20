"""POST /api/v1/runs — inline benchmark execution."""

import pytest
from httpx import ASGITransport, AsyncClient
from redis.exceptions import ConnectionError as RedisConnectionError

from app.database import async_session_maker
from app.main import app
from app.models import Dataset, PipelineConfig, QueryCase
from tests.conftest import make_upload

BASE = "/api/v1"
DOC_A = (
    "Retrieval-Augmented Generation combines retrieval with language model generation. "
    "Dense vector similarity is used to find relevant passages from a corpus."
)
DOC_B = (
    "Photosynthesis converts sunlight into chemical energy. "
    "Chlorophyll in plant cells absorbs light, primarily in the blue and red wavelengths."
)


@pytest.fixture
async def run_create_client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def _upload(c: AsyncClient, filename: str, content: str) -> int:
    resp = await c.post(
        f"{BASE}/documents",
        params={"chunk_size": 200},
        files=make_upload(filename, content),
    )
    assert resp.status_code == 201
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_create_run_heuristic_success(run_create_client: AsyncClient):
    await _upload(run_create_client, "rag_create.txt", DOC_A)

    async with async_session_maker() as session:
        ds = Dataset(name="create_ds", description="")
        session.add(ds)
        await session.flush()
        qc = QueryCase(
            dataset_id=ds.id,
            query_text="What is RAG?",
            expected_answer="Retrieval augmented generation.",
        )
        pc = PipelineConfig(
            name="create_pc",
            embedding_model="all-MiniLM-L6-v2",
            chunk_strategy="fixed",
            chunk_size=200,
            chunk_overlap=0,
            top_k=3,
        )
        session.add_all([qc, pc])
        await session.commit()
        qc_id, pc_id = qc.id, pc.id

    resp = await run_create_client.post(
        f"{BASE}/runs",
        json={
            "query_case_id": qc_id,
            "pipeline_config_id": pc_id,
            "eval_mode": "heuristic",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "completed"
    assert data["eval_mode"] == "heuristic"
    assert isinstance(data["run_id"], int)

    detail = await run_create_client.get(f"{BASE}/runs/{data['run_id']}")
    assert detail.status_code == 200
    assert detail.json()["evaluator_type"] == "heuristic"


@pytest.mark.asyncio
async def test_create_run_heuristic_with_document_id_success(run_create_client: AsyncClient):
    doc_a_id = await _upload(run_create_client, "rag_scoped.txt", DOC_A)
    await _upload(run_create_client, "bio_scoped.txt", DOC_B)

    async with async_session_maker() as session:
        ds = Dataset(name="scoped_ds", description="")
        session.add(ds)
        await session.flush()
        qc = QueryCase(
            dataset_id=ds.id,
            query_text="What is RAG?",
            expected_answer="RAG combines retrieval with generation.",
        )
        pc = PipelineConfig(
            name="scoped_pc",
            embedding_model="all-MiniLM-L6-v2",
            chunk_strategy="fixed",
            chunk_size=200,
            chunk_overlap=0,
            top_k=5,
        )
        session.add_all([qc, pc])
        await session.commit()
        qc_id, pc_id = qc.id, pc.id

    resp = await run_create_client.post(
        f"{BASE}/runs",
        json={
            "query_case_id": qc_id,
            "pipeline_config_id": pc_id,
            "eval_mode": "heuristic",
            "document_id": doc_a_id,
        },
    )
    assert resp.status_code == 201
    rid = resp.json()["run_id"]

    detail = await run_create_client.get(f"{BASE}/runs/{rid}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["evaluator_type"] == "heuristic"
    for hit in body["retrieval_hits"]:
        assert hit["document_id"] == doc_a_id


@pytest.mark.asyncio
async def test_create_run_invalid_document_id_returns_404(run_create_client: AsyncClient):
    async with async_session_maker() as session:
        ds = Dataset(name="doc404_ds", description="")
        session.add(ds)
        await session.flush()
        qc = QueryCase(dataset_id=ds.id, query_text="q", expected_answer=None)
        pc = PipelineConfig(
            name="doc404_pc",
            embedding_model="all-MiniLM-L6-v2",
            chunk_strategy="fixed",
            chunk_size=200,
            chunk_overlap=0,
            top_k=3,
        )
        session.add_all([qc, pc])
        await session.commit()
        qc_id, pc_id = qc.id, pc.id

    resp = await run_create_client.post(
        f"{BASE}/runs",
        json={
            "query_case_id": qc_id,
            "pipeline_config_id": pc_id,
            "eval_mode": "heuristic",
            "document_id": 999_999,
        },
    )
    assert resp.status_code == 404
    assert "document" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_create_run_invalid_query_case_returns_404(run_create_client: AsyncClient):
    async with async_session_maker() as session:
        pc = PipelineConfig(
            name="orphan_pc",
            embedding_model="all-MiniLM-L6-v2",
            chunk_strategy="fixed",
            chunk_size=200,
            chunk_overlap=0,
            top_k=3,
        )
        session.add(pc)
        await session.commit()
        pc_id = pc.id

    resp = await run_create_client.post(
        f"{BASE}/runs",
        json={"query_case_id": 999_999, "pipeline_config_id": pc_id, "eval_mode": "heuristic"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_create_run_invalid_pipeline_config_returns_404(run_create_client: AsyncClient):
    async with async_session_maker() as session:
        ds = Dataset(name="ds2", description="")
        session.add(ds)
        await session.flush()
        qc = QueryCase(dataset_id=ds.id, query_text="hi", expected_answer=None)
        session.add(qc)
        await session.commit()
        qc_id = qc.id

    resp = await run_create_client.post(
        f"{BASE}/runs",
        json={"query_case_id": qc_id, "pipeline_config_id": 888_888, "eval_mode": "heuristic"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_create_run_invalid_eval_mode_returns_422(run_create_client: AsyncClient):
    resp = await run_create_client.post(
        f"{BASE}/runs",
        json={"query_case_id": 1, "pipeline_config_id": 1, "eval_mode": "not_a_mode"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_run_full_without_api_key_fails_cleanly(
    run_create_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    await _upload(run_create_client, "rag_full.txt", DOC_A)

    async with async_session_maker() as session:
        ds = Dataset(name="full_ds", description="")
        session.add(ds)
        await session.flush()
        qc = QueryCase(
            dataset_id=ds.id,
            query_text="What is RAG?",
            expected_answer="x",
        )
        pc = PipelineConfig(
            name="full_pc",
            embedding_model="all-MiniLM-L6-v2",
            chunk_strategy="fixed",
            chunk_size=200,
            chunk_overlap=0,
            top_k=3,
        )
        session.add_all([qc, pc])
        await session.commit()
        qc_id, pc_id = qc.id, pc.id

    def _boom() -> None:
        raise ValueError(
            "claude_api_key / CLAUDE_API_KEY is not set. Required for generation and LLM judge."
        )

    monkeypatch.setattr("app.services.run_create.require_api_key", _boom)

    resp = await run_create_client.post(
        f"{BASE}/runs",
        json={"query_case_id": qc_id, "pipeline_config_id": pc_id, "eval_mode": "full"},
    )
    assert resp.status_code == 503
    assert "claude_api_key" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_create_run_full_returns_202_and_run_stays_running_when_worker_noops(
    run_create_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    """Full mode returns immediately; RQ job is enqueued (noop worker = run stays running)."""
    await _upload(run_create_client, "rag_202.txt", DOC_A)

    async with async_session_maker() as session:
        ds = Dataset(name="full202_ds", description="")
        session.add(ds)
        await session.flush()
        qc = QueryCase(
            dataset_id=ds.id,
            query_text="What is RAG?",
            expected_answer="x",
        )
        pc = PipelineConfig(
            name="full202_pc",
            embedding_model="all-MiniLM-L6-v2",
            chunk_strategy="fixed",
            chunk_size=200,
            chunk_overlap=0,
            top_k=3,
        )
        session.add_all([qc, pc])
        await session.commit()
        qc_id, pc_id = qc.id, pc.id

    monkeypatch.setattr("app.services.run_create.require_api_key", lambda: None)

    monkeypatch.setattr(
        "app.api.runs.enqueue_full_benchmark_run",
        lambda _run_id, _document_id=None: "test-rq-job-id",
    )

    resp = await run_create_client.post(
        f"{BASE}/runs",
        json={"query_case_id": qc_id, "pipeline_config_id": pc_id, "eval_mode": "full"},
    )
    assert resp.status_code == 202
    data = resp.json()
    assert data["status"] == "running"
    assert data["eval_mode"] == "full"
    assert data.get("job_id") == "test-rq-job-id"
    rid = data["run_id"]

    detail = await run_create_client.get(f"{BASE}/runs/{rid}")
    assert detail.status_code == 200
    assert detail.json()["status"] == "running"


@pytest.mark.asyncio
async def test_create_run_full_redis_unavailable_returns_503(
    run_create_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    await _upload(run_create_client, "rag_redis503.txt", DOC_A)

    async with async_session_maker() as session:
        ds = Dataset(name="redis503_ds", description="")
        session.add(ds)
        await session.flush()
        qc = QueryCase(
            dataset_id=ds.id,
            query_text="What is RAG?",
            expected_answer="x",
        )
        pc = PipelineConfig(
            name="redis503_pc",
            embedding_model="all-MiniLM-L6-v2",
            chunk_strategy="fixed",
            chunk_size=200,
            chunk_overlap=0,
            top_k=3,
        )
        session.add_all([qc, pc])
        await session.commit()
        qc_id, pc_id = qc.id, pc.id

    monkeypatch.setattr("app.services.run_create.require_api_key", lambda: None)

    def _boom(_run_id: int, _document_id: int | None = None) -> str:
        raise RedisConnectionError("Redis unavailable")

    monkeypatch.setattr("app.api.runs.enqueue_full_benchmark_run", _boom)

    resp = await run_create_client.post(
        f"{BASE}/runs",
        json={"query_case_id": qc_id, "pipeline_config_id": pc_id, "eval_mode": "full"},
    )
    assert resp.status_code == 503
    assert "queue" in resp.json()["detail"].lower() or "redis" in resp.json()["detail"].lower()
