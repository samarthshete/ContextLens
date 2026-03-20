"""GET /api/v1/query-cases — read-only registry."""

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
async def test_list_query_cases_filter_by_dataset(api_client: AsyncClient):
    async with async_session_maker() as session:
        d1 = Dataset(name="d1", description="")
        d2 = Dataset(name="d2", description="")
        session.add_all([d1, d2])
        await session.flush()
        session.add_all(
            [
                QueryCase(dataset_id=d1.id, query_text="q1", expected_answer="a1"),
                QueryCase(dataset_id=d1.id, query_text="q2", expected_answer=None),
                QueryCase(dataset_id=d2.id, query_text="q3", expected_answer="a3"),
            ]
        )
        await session.commit()
        d1_id = d1.id

    resp = await api_client.get(f"{BASE}/query-cases", params={"dataset_id": d1_id})
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 2
    assert all(x["dataset_id"] == d1_id for x in items)
    texts = sorted(x["query_text"] for x in items)
    assert texts == ["q1", "q2"]


@pytest.mark.asyncio
async def test_list_query_cases_filter_unknown_dataset_404(api_client: AsyncClient):
    resp = await api_client.get(f"{BASE}/query-cases", params={"dataset_id": 888888})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_query_cases_all_stable_order(api_client: AsyncClient):
    async with async_session_maker() as session:
        d = Dataset(name="da", description="")
        session.add(d)
        await session.flush()
        session.add(QueryCase(dataset_id=d.id, query_text="z", expected_answer=None))
        await session.commit()

    resp = await api_client.get(f"{BASE}/query-cases")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_get_query_case_by_id(api_client: AsyncClient):
    async with async_session_maker() as session:
        d = Dataset(name="dq", description="")
        session.add(d)
        await session.flush()
        qc = QueryCase(dataset_id=d.id, query_text="hello world", expected_answer="hw")
        session.add(qc)
        await session.commit()
        qid = qc.id

    resp = await api_client.get(f"{BASE}/query-cases/{qid}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == qid
    assert body["query_text"] == "hello world"
    assert body["expected_answer"] == "hw"


@pytest.mark.asyncio
async def test_get_query_case_404(api_client: AsyncClient):
    resp = await api_client.get(f"{BASE}/query-cases/999999")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_post_query_case_201(api_client: AsyncClient):
    async with async_session_maker() as session:
        d = Dataset(name="parent_ds", description="")
        session.add(d)
        await session.commit()
        did = d.id

    resp = await api_client.post(
        f"{BASE}/query-cases",
        json={
            "dataset_id": did,
            "query_text": "What is the benchmark?",
            "expected_answer": "42",
            "metadata_json": {"k": "v"},
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["dataset_id"] == did
    assert body["query_text"] == "What is the benchmark?"
    assert body["expected_answer"] == "42"
    assert body["metadata_json"] == {"k": "v"}


@pytest.mark.asyncio
async def test_post_query_case_invalid_dataset_404(api_client: AsyncClient):
    resp = await api_client.post(
        f"{BASE}/query-cases",
        json={"dataset_id": 999888, "query_text": "orphan question"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_patch_query_case_200(api_client: AsyncClient):
    async with async_session_maker() as session:
        d = Dataset(name="d_patch", description="")
        session.add(d)
        await session.flush()
        qc = QueryCase(dataset_id=d.id, query_text="old q", expected_answer="old a")
        session.add(qc)
        await session.commit()
        qid = qc.id

    resp = await api_client.patch(
        f"{BASE}/query-cases/{qid}",
        json={"query_text": "new q"},
    )
    assert resp.status_code == 200
    assert resp.json()["query_text"] == "new q"
    assert resp.json()["expected_answer"] == "old a"


@pytest.mark.asyncio
async def test_patch_query_case_404(api_client: AsyncClient):
    async with async_session_maker() as session:
        d = Dataset(name="d_only", description="")
        session.add(d)
        await session.commit()
        did = d.id

    resp = await api_client.patch(
        f"{BASE}/query-cases/999999",
        json={"dataset_id": did},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_patch_query_case_invalid_dataset_404(api_client: AsyncClient):
    async with async_session_maker() as session:
        d = Dataset(name="d_ok", description="")
        session.add(d)
        await session.flush()
        qc = QueryCase(dataset_id=d.id, query_text="q", expected_answer=None)
        session.add(qc)
        await session.commit()
        qid = qc.id

    resp = await api_client.patch(
        f"{BASE}/query-cases/{qid}",
        json={"dataset_id": 999777},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_query_case_204_when_no_runs(api_client: AsyncClient):
    async with async_session_maker() as session:
        d = Dataset(name="d_del_qc", description="")
        session.add(d)
        await session.flush()
        qc = QueryCase(dataset_id=d.id, query_text="to delete")
        session.add(qc)
        await session.commit()
        qid = qc.id

    resp = await api_client.delete(f"{BASE}/query-cases/{qid}")
    assert resp.status_code == 204
    assert (await api_client.get(f"{BASE}/query-cases/{qid}")).status_code == 404


@pytest.mark.asyncio
async def test_delete_query_case_404(api_client: AsyncClient):
    assert (await api_client.delete(f"{BASE}/query-cases/999995")).status_code == 404


@pytest.mark.asyncio
async def test_delete_query_case_409_when_run(api_client: AsyncClient):
    async with async_session_maker() as session:
        d = Dataset(name="d_run_block", description="")
        session.add(d)
        await session.flush()
        qc = QueryCase(dataset_id=d.id, query_text="has run")
        session.add(qc)
        await session.flush()
        pc = PipelineConfig(
            name="pc_for_run",
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
        qid = qc.id

    resp = await api_client.delete(f"{BASE}/query-cases/{qid}")
    assert resp.status_code == 409
    get_r = await api_client.get(f"{BASE}/query-cases/{qid}")
    assert get_r.status_code == 200
    assert get_r.json()["query_text"] == "has run"
