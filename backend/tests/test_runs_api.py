"""Run inspection API."""

from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient

from app.database import async_session_maker
from app.main import app
from app.models import (
    Chunk,
    Dataset,
    Document,
    EvaluationResult,
    PipelineConfig,
    QueryCase,
    RetrievalResult,
    Run,
)
from app.services.run_lifecycle import STATUS_COMPLETED

BASE = "/api/v1"


@pytest.fixture
async def run_client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_get_run_detail_returns_trace(run_client: AsyncClient):
    async with async_session_maker() as session:
        ds = Dataset(name="api_ds", description="")
        session.add(ds)
        await session.flush()
        qc = QueryCase(
            dataset_id=ds.id,
            query_text="What is up?",
            expected_answer="sky",
        )
        pc = PipelineConfig(
            name="api_pc",
            embedding_model="all-MiniLM-L6-v2",
            chunk_strategy="fixed",
            chunk_size=50,
            chunk_overlap=0,
            top_k=2,
        )
        session.add_all([qc, pc])
        await session.flush()
        doc = Document(
            title="t.txt",
            source_type="txt",
            file_path="seed://runs_api",
            raw_text="hi",
            status="processed",
        )
        session.add(doc)
        await session.flush()
        ch = Chunk(
            document_id=doc.id,
            content="hello world",
            chunk_index=0,
            start_char=0,
            end_char=11,
        )
        session.add(ch)
        await session.flush()
        run = Run(
            query_case_id=qc.id,
            pipeline_config_id=pc.id,
            status=STATUS_COMPLETED,
            retrieval_latency_ms=10,
            evaluation_latency_ms=5,
            total_latency_ms=15,
        )
        session.add(run)
        await session.flush()
        session.add(RetrievalResult(run_id=run.id, chunk_id=ch.id, rank=1, score=0.88))
        session.add(
            EvaluationResult(
                run_id=run.id,
                faithfulness=0.9,
                completeness=0.8,
                retrieval_relevance=0.7,
                context_coverage=0.6,
                groundedness=0.85,
                failure_type="NO_FAILURE",
                used_llm_judge=True,
                metadata_json={"evaluator_type": "llm"},
                cost_usd=Decimal("0.01"),
            )
        )
        await session.commit()
        rid = run.id

    resp = await run_client.get(f"{BASE}/runs/{rid}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["run_id"] == rid
    assert body["evaluator_type"] == "llm"
    assert body["query_case"]["query_text"] == "What is up?"
    assert body["pipeline_config"]["top_k"] == 2
    assert len(body["retrieval_hits"]) == 1
    assert body["retrieval_hits"][0]["rank"] == 1
    assert body["retrieval_hits"][0]["score"] == pytest.approx(0.88)
    assert "hello" in body["retrieval_hits"][0]["content"]
    assert body["generation"] is None
    assert body["evaluation"]["faithfulness"] == pytest.approx(0.9)
    assert body["evaluation"]["groundedness"] == pytest.approx(0.85)
    assert body["evaluation"]["failure_type"] == "NO_FAILURE"
    assert body["evaluation"]["used_llm_judge"] is True
    assert body["retrieval_latency_ms"] == 10


@pytest.mark.asyncio
async def test_get_run_detail_404(run_client: AsyncClient):
    resp = await run_client.get(f"{BASE}/runs/999999")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_runs_and_config_comparison(run_client: AsyncClient):
    """Paginated listing + config comparison buckets (heuristic vs LLM)."""
    async with async_session_maker() as session:
        ds = Dataset(name="list_ds", description="")
        session.add(ds)
        await session.flush()
        qc1 = QueryCase(
            dataset_id=ds.id,
            query_text="q1",
            expected_answer="a1",
        )
        qc2 = QueryCase(
            dataset_id=ds.id,
            query_text="q2",
            expected_answer="a2",
        )
        pc_h = PipelineConfig(
            name="pc_heur",
            embedding_model="all-MiniLM-L6-v2",
            chunk_strategy="fixed",
            chunk_size=50,
            chunk_overlap=0,
            top_k=2,
        )
        pc_l = PipelineConfig(
            name="pc_llm",
            embedding_model="all-MiniLM-L6-v2",
            chunk_strategy="fixed",
            chunk_size=50,
            chunk_overlap=0,
            top_k=3,
        )
        session.add_all([qc1, qc2, pc_h, pc_l])
        await session.flush()
        doc = Document(
            title="t2.txt",
            source_type="txt",
            file_path="seed://list_runs",
            raw_text="x",
            status="processed",
        )
        session.add(doc)
        await session.flush()
        ch = Chunk(
            document_id=doc.id,
            content="chunk",
            chunk_index=0,
            start_char=0,
            end_char=5,
        )
        session.add(ch)
        await session.flush()

        run_h = Run(
            query_case_id=qc1.id,
            pipeline_config_id=pc_h.id,
            status=STATUS_COMPLETED,
            retrieval_latency_ms=100,
            evaluation_latency_ms=20,
            total_latency_ms=120,
        )
        run_l = Run(
            query_case_id=qc2.id,
            pipeline_config_id=pc_l.id,
            status=STATUS_COMPLETED,
            retrieval_latency_ms=200,
            evaluation_latency_ms=40,
            total_latency_ms=240,
        )
        session.add_all([run_h, run_l])
        await session.flush()
        session.add(RetrievalResult(run_id=run_h.id, chunk_id=ch.id, rank=1, score=0.5))
        session.add(RetrievalResult(run_id=run_l.id, chunk_id=ch.id, rank=1, score=0.6))
        session.add(
            EvaluationResult(
                run_id=run_h.id,
                faithfulness=None,
                completeness=None,
                retrieval_relevance=0.5,
                context_coverage=0.5,
                groundedness=None,
                failure_type="RETRIEVAL_MISS",
                used_llm_judge=False,
                metadata_json={"evaluator_type": "heuristic"},
            )
        )
        session.add(
            EvaluationResult(
                run_id=run_l.id,
                faithfulness=0.9,
                completeness=0.8,
                retrieval_relevance=0.7,
                context_coverage=0.6,
                groundedness=0.85,
                failure_type="NO_FAILURE",
                used_llm_judge=True,
                metadata_json={"evaluator_type": "llm"},
                cost_usd=Decimal("0.02"),
            )
        )
        await session.commit()
        ds_id = ds.id
        pid_h = pc_h.id
        pid_l = pc_l.id
        rid_h = run_h.id
        rid_l = run_l.id

    r_list = await run_client.get(
        f"{BASE}/runs",
        params={"dataset_id": ds_id, "limit": 10, "offset": 0},
    )
    assert r_list.status_code == 200
    body = r_list.json()
    assert body["total"] == 2
    assert len(body["items"]) == 2
    # Newest first: run_l inserted after run_h
    assert body["items"][0]["run_id"] == rid_l
    assert body["items"][1]["run_id"] == rid_h

    r_llm = await run_client.get(f"{BASE}/runs", params={"evaluator_type": "llm"})
    assert r_llm.status_code == 200
    llm_ids = {it["run_id"] for it in r_llm.json()["items"]}
    assert rid_l in llm_ids
    assert rid_h not in llm_ids

    r_heur = await run_client.get(f"{BASE}/runs", params={"evaluator_type": "heuristic"})
    assert r_heur.status_code == 200
    heur_ids = {it["run_id"] for it in r_heur.json()["items"]}
    assert rid_h in heur_ids

    cmp_resp = await run_client.get(
        f"{BASE}/runs/config-comparison",
        params=[
            ("pipeline_config_ids", pid_h),
            ("pipeline_config_ids", pid_l),
            ("evaluator_type", "both"),
        ],
    )
    assert cmp_resp.status_code == 200
    cmp_body = cmp_resp.json()
    assert cmp_body["evaluator_type"] == "both"
    assert cmp_body["configs"] is None
    b = cmp_body["buckets"]
    h_by = {x["pipeline_config_id"]: x for x in b["heuristic"]}
    l_by = {x["pipeline_config_id"]: x for x in b["llm"]}
    assert h_by[pid_h]["traced_runs"] == 1
    assert h_by[pid_l]["traced_runs"] == 0
    assert l_by[pid_h]["traced_runs"] == 0
    assert l_by[pid_l]["traced_runs"] == 1
    assert l_by[pid_l]["avg_groundedness"] == pytest.approx(0.85)

    comb = await run_client.get(
        f"{BASE}/runs/config-comparison",
        params=[
            ("pipeline_config_ids", pid_l),
            ("combine_evaluators", "true"),
        ],
    )
    assert comb.status_code == 200
    cj = comb.json()
    assert cj["evaluator_type"] == "combined"
    assert len(cj["configs"]) == 1
    assert cj["configs"][0]["traced_runs"] == 1
