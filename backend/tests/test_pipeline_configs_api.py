"""GET /api/v1/pipeline-configs — read-only registry."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.database import async_session_maker
from app.main import app
from app.models import Dataset, PipelineConfig, QueryCase, Run

BASE = "/api/v1"


@pytest.fixture
async def api_client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_list_pipeline_configs(api_client: AsyncClient):
    async with async_session_maker() as session:
        session.add_all(
            [
                PipelineConfig(
                    name="pc_a",
                    embedding_model="all-MiniLM-L6-v2",
                    chunk_strategy="fixed",
                    chunk_size=100,
                    chunk_overlap=0,
                    top_k=5,
                ),
                PipelineConfig(
                    name="pc_b",
                    embedding_model="all-MiniLM-L6-v2",
                    chunk_strategy="recursive",
                    chunk_size=200,
                    chunk_overlap=10,
                    top_k=8,
                ),
            ]
        )
        await session.commit()

    resp = await api_client.get(f"{BASE}/pipeline-configs")
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) >= 2
    names = {x["name"] for x in items}
    assert "pc_a" in names and "pc_b" in names
    row = next(x for x in items if x["name"] == "pc_b")
    assert row["top_k"] == 8
    assert row["chunk_strategy"] == "recursive"
    assert "created_at" in row


@pytest.mark.asyncio
async def test_get_pipeline_config_by_id(api_client: AsyncClient):
    async with async_session_maker() as session:
        pc = PipelineConfig(
            name="solo_pc",
            embedding_model="all-MiniLM-L6-v2",
            chunk_strategy="fixed",
            chunk_size=50,
            chunk_overlap=0,
            top_k=3,
        )
        session.add(pc)
        await session.commit()
        pid = pc.id

    resp = await api_client.get(f"{BASE}/pipeline-configs/{pid}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == pid
    assert body["name"] == "solo_pc"
    assert body["top_k"] == 3


@pytest.mark.asyncio
async def test_get_pipeline_config_404(api_client: AsyncClient):
    resp = await api_client.get(f"{BASE}/pipeline-configs/999999")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_post_pipeline_config_201(api_client: AsyncClient):
    resp = await api_client.post(
        f"{BASE}/pipeline-configs",
        json={
            "name": "api_pc",
            "embedding_model": "all-MiniLM-L6-v2",
            "chunk_strategy": "fixed",
            "chunk_size": 120,
            "chunk_overlap": 10,
            "top_k": 6,
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "api_pc"
    assert body["chunk_size"] == 120
    assert body["chunk_overlap"] == 10
    assert body["top_k"] == 6


@pytest.mark.asyncio
async def test_post_pipeline_config_overlap_gt_size_422(api_client: AsyncClient):
    resp = await api_client.post(
        f"{BASE}/pipeline-configs",
        json={
            "name": "bad_pc",
            "embedding_model": "all-MiniLM-L6-v2",
            "chunk_strategy": "fixed",
            "chunk_size": 50,
            "chunk_overlap": 51,
            "top_k": 3,
        },
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_patch_pipeline_config_200(api_client: AsyncClient):
    async with async_session_maker() as session:
        pc = PipelineConfig(
            name="pc_patch",
            embedding_model="all-MiniLM-L6-v2",
            chunk_strategy="fixed",
            chunk_size=100,
            chunk_overlap=0,
            top_k=5,
        )
        session.add(pc)
        await session.commit()
        pid = pc.id

    resp = await api_client.patch(
        f"{BASE}/pipeline-configs/{pid}",
        json={"top_k": 9, "chunk_overlap": 5},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["top_k"] == 9
    assert body["chunk_overlap"] == 5
    assert body["chunk_size"] == 100


@pytest.mark.asyncio
async def test_patch_pipeline_config_invalid_combo_422(api_client: AsyncClient):
    async with async_session_maker() as session:
        pc = PipelineConfig(
            name="pc_bad_patch",
            embedding_model="all-MiniLM-L6-v2",
            chunk_strategy="fixed",
            chunk_size=20,
            chunk_overlap=0,
            top_k=2,
        )
        session.add(pc)
        await session.commit()
        pid = pc.id

    resp = await api_client.patch(
        f"{BASE}/pipeline-configs/{pid}",
        json={"chunk_overlap": 50},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_patch_pipeline_config_404(api_client: AsyncClient):
    resp = await api_client.patch(
        f"{BASE}/pipeline-configs/999999",
        json={"name": "ghost"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_pipeline_config_204_when_no_runs(api_client: AsyncClient):
    async with async_session_maker() as session:
        pc = PipelineConfig(
            name="pc_delete_ok",
            embedding_model="all-MiniLM-L6-v2",
            chunk_strategy="fixed",
            chunk_size=100,
            chunk_overlap=0,
            top_k=5,
        )
        session.add(pc)
        await session.commit()
        pid = pc.id

    resp = await api_client.delete(f"{BASE}/pipeline-configs/{pid}")
    assert resp.status_code == 204
    assert (await api_client.get(f"{BASE}/pipeline-configs/{pid}")).status_code == 404


@pytest.mark.asyncio
async def test_delete_pipeline_config_404(api_client: AsyncClient):
    assert (await api_client.delete(f"{BASE}/pipeline-configs/999994")).status_code == 404


@pytest.mark.asyncio
async def test_delete_pipeline_config_409_when_run(api_client: AsyncClient):
    async with async_session_maker() as session:
        d = Dataset(name="d_pc_block", description="")
        session.add(d)
        await session.flush()
        qc = QueryCase(dataset_id=d.id, query_text="q")
        session.add(qc)
        await session.flush()
        pc = PipelineConfig(
            name="pc_blocked",
            embedding_model="all-MiniLM-L6-v2",
            chunk_strategy="fixed",
            chunk_size=100,
            chunk_overlap=0,
            top_k=5,
        )
        session.add(pc)
        await session.flush()
        session.add(Run(query_case_id=qc.id, pipeline_config_id=pc.id, status="completed"))
        await session.commit()
        pid = pc.id

    resp = await api_client.delete(f"{BASE}/pipeline-configs/{pid}")
    assert resp.status_code == 409
    get_r = await api_client.get(f"{BASE}/pipeline-configs/{pid}")
    assert get_r.status_code == 200
    assert get_r.json()["name"] == "pc_blocked"
