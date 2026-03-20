"""GET/POST/PATCH/DELETE /api/v1/datasets — registry."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.database import async_session_maker
from app.main import app
from app.models import Dataset, QueryCase

BASE = "/api/v1"


@pytest.fixture
async def api_client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_list_datasets_newest_first(api_client: AsyncClient):
    async with async_session_maker() as session:
        session.add_all(
            [
                Dataset(name="older_ds", description="a"),
                Dataset(name="newer_ds", description="b"),
            ]
        )
        await session.commit()

    resp = await api_client.get(f"{BASE}/datasets")
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) >= 2
    names = [x["name"] for x in items]
    # Newer row should appear before older (same-second inserts: id tie-break in service)
    idx_newer = names.index("newer_ds")
    idx_older = names.index("older_ds")
    assert idx_newer < idx_older
    for x in items:
        assert "id" in x and "name" in x and "created_at" in x
        assert "description" in x


@pytest.mark.asyncio
async def test_get_dataset_by_id(api_client: AsyncClient):
    async with async_session_maker() as session:
        ds = Dataset(name="single_ds", description="hello")
        session.add(ds)
        await session.commit()
        did = ds.id

    resp = await api_client.get(f"{BASE}/datasets/{did}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == did
    assert body["name"] == "single_ds"
    assert body["description"] == "hello"


@pytest.mark.asyncio
async def test_get_dataset_404(api_client: AsyncClient):
    resp = await api_client.get(f"{BASE}/datasets/999999")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_post_dataset_201(api_client: AsyncClient):
    resp = await api_client.post(
        f"{BASE}/datasets",
        json={"name": "  api_created_ds  ", "description": "via http", "metadata_json": {"source": "test"}},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "api_created_ds"
    assert body["description"] == "via http"
    assert body["metadata_json"] == {"source": "test"}
    assert "id" in body and "created_at" in body


@pytest.mark.asyncio
async def test_post_dataset_empty_name_422(api_client: AsyncClient):
    resp = await api_client.post(f"{BASE}/datasets", json={"name": "   "})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_patch_dataset_200(api_client: AsyncClient):
    async with async_session_maker() as session:
        ds = Dataset(name="patch_me", description="old")
        session.add(ds)
        await session.commit()
        did = ds.id

    resp = await api_client.patch(
        f"{BASE}/datasets/{did}",
        json={"name": "patched_name", "description": None},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "patched_name"
    assert body["description"] is None


@pytest.mark.asyncio
async def test_patch_dataset_404(api_client: AsyncClient):
    resp = await api_client.patch(
        f"{BASE}/datasets/999999",
        json={"name": "nope"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_dataset_204_when_no_query_cases(api_client: AsyncClient):
    async with async_session_maker() as session:
        ds = Dataset(name="delete_empty_ds", description="")
        session.add(ds)
        await session.commit()
        did = ds.id

    resp = await api_client.delete(f"{BASE}/datasets/{did}")
    assert resp.status_code == 204
    assert (await api_client.get(f"{BASE}/datasets/{did}")).status_code == 404


@pytest.mark.asyncio
async def test_delete_dataset_404(api_client: AsyncClient):
    assert (await api_client.delete(f"{BASE}/datasets/999996")).status_code == 404


@pytest.mark.asyncio
async def test_delete_dataset_409_when_query_cases(api_client: AsyncClient):
    async with async_session_maker() as session:
        ds = Dataset(name="has_qc_ds", description="")
        session.add(ds)
        await session.flush()
        session.add(QueryCase(dataset_id=ds.id, query_text="blocked"))
        await session.commit()
        did = ds.id

    resp = await api_client.delete(f"{BASE}/datasets/{did}")
    assert resp.status_code == 409
    get_r = await api_client.get(f"{BASE}/datasets/{did}")
    assert get_r.status_code == 200
    assert get_r.json()["name"] == "has_qc_ds"
