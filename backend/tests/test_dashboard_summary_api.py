"""GET /api/v1/runs/dashboard-summary."""

import pytest
from fastapi import APIRouter, FastAPI
from httpx import ASGITransport, AsyncClient

from app.database import async_session_maker
from app.main import app
from decimal import Decimal

from app.models import (
    Chunk,
    Dataset,
    Document,
    EvaluationResult,
    GenerationResult,
    PipelineConfig,
    QueryCase,
    RetrievalResult,
    Run,
)
from app.services.run_lifecycle import STATUS_COMPLETED, STATUS_FAILED, STATUS_RUNNING

BASE = "/api/v1"


@pytest.fixture
async def dash_client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def _seed_run_with_eval(
    session,
    *,
    status: str,
    failure_type: str,
    cost: float | None,
    run_metadata: dict | None = None,
    retrieval_latency_ms: int = 10,
    generation_latency_ms: int = 20,
    evaluation_latency_ms: int = 30,
    total_latency_ms: int = 60,
):
    ds = Dataset(name="dash_ds", description="")
    session.add(ds)
    await session.flush()
    qc = QueryCase(dataset_id=ds.id, query_text="q?", expected_answer=None)
    pc = PipelineConfig(
        name="dash_pc",
        embedding_model="all-MiniLM-L6-v2",
        chunk_strategy="fixed",
        chunk_size=100,
        chunk_overlap=0,
        top_k=3,
    )
    session.add_all([qc, pc])
    await session.flush()
    run = Run(
        query_case_id=qc.id,
        pipeline_config_id=pc.id,
        status=status,
        metadata_json=run_metadata,
        retrieval_latency_ms=retrieval_latency_ms,
        generation_latency_ms=generation_latency_ms,
        evaluation_latency_ms=evaluation_latency_ms,
        total_latency_ms=total_latency_ms,
    )
    session.add(run)
    await session.flush()
    session.add(
        EvaluationResult(
            run_id=run.id,
            faithfulness=0.5,
            completeness=0.5,
            retrieval_relevance=0.5,
            context_coverage=0.5,
            failure_type=failure_type,
            used_llm_judge=True,
            metadata_json={"evaluator_type": "llm"},
            cost_usd=cost,
        )
    )
    await session.commit()
    return run.id


async def _seed_one_traced_run_with_corpus(session) -> None:
    """One run with retrieval + evaluation + one processed document and chunk (for scale deltas)."""
    ds = Dataset(name="scale_ds", description="")
    session.add(ds)
    await session.flush()
    qc = QueryCase(dataset_id=ds.id, query_text="scale q", expected_answer=None)
    pc = PipelineConfig(
        name="scale_pc",
        embedding_model="all-MiniLM-L6-v2",
        chunk_strategy="fixed",
        chunk_size=100,
        chunk_overlap=0,
        top_k=3,
    )
    session.add_all([qc, pc])
    await session.flush()
    doc = Document(
        title="scale.txt",
        source_type="txt",
        file_path="seed://scale_dash",
        raw_text="hello",
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
    session.add(RetrievalResult(run_id=run.id, chunk_id=ch.id, rank=1, score=0.9))
    session.add(
        EvaluationResult(
            run_id=run.id,
            faithfulness=0.8,
            completeness=0.7,
            retrieval_relevance=0.6,
            context_coverage=0.5,
            failure_type="NO_FAILURE",
            used_llm_judge=True,
            metadata_json={"evaluator_type": "llm"},
            cost_usd=Decimal("0.001"),
        )
    )
    await session.commit()


async def _seed_heuristic_run(session, *, cost: float | None = None) -> int:
    """Heuristic evaluation row (no LLM judge path — cost should stay null in honest data)."""
    ds = Dataset(name="dash_heur_ds", description="")
    session.add(ds)
    await session.flush()
    qc = QueryCase(dataset_id=ds.id, query_text="hq", expected_answer=None)
    pc = PipelineConfig(
        name="dash_heur_pc",
        embedding_model="all-MiniLM-L6-v2",
        chunk_strategy="fixed",
        chunk_size=100,
        chunk_overlap=0,
        top_k=3,
    )
    session.add_all([qc, pc])
    await session.flush()
    run = Run(
        query_case_id=qc.id,
        pipeline_config_id=pc.id,
        status=STATUS_COMPLETED,
        retrieval_latency_ms=5,
        evaluation_latency_ms=5,
        total_latency_ms=10,
    )
    session.add(run)
    await session.flush()
    session.add(
        EvaluationResult(
            run_id=run.id,
            faithfulness=None,
            completeness=0.5,
            retrieval_relevance=0.5,
            context_coverage=0.5,
            failure_type="NO_FAILURE",
            used_llm_judge=False,
            metadata_json={"evaluator_type": "heuristic"},
            cost_usd=cost,
        )
    )
    await session.commit()
    return run.id


async def _seed_full_rag_llm_run(session, *, cost: float) -> int:
    """Run with ``generation_results`` + LLM judge evaluation (measured cost)."""
    ds = Dataset(name="dash_fr_ds", description="")
    session.add(ds)
    await session.flush()
    qc = QueryCase(dataset_id=ds.id, query_text="fq", expected_answer=None)
    pc = PipelineConfig(
        name="dash_fr_pc",
        embedding_model="all-MiniLM-L6-v2",
        chunk_strategy="fixed",
        chunk_size=100,
        chunk_overlap=0,
        top_k=3,
    )
    session.add_all([qc, pc])
    await session.flush()
    run = Run(
        query_case_id=qc.id,
        pipeline_config_id=pc.id,
        status=STATUS_COMPLETED,
        retrieval_latency_ms=5,
        generation_latency_ms=10,
        evaluation_latency_ms=5,
        total_latency_ms=20,
    )
    session.add(run)
    await session.flush()
    session.add(
        GenerationResult(
            run_id=run.id,
            answer_text="answer",
            model_id="gpt-test",
            input_tokens=1,
            output_tokens=1,
        )
    )
    session.add(
        EvaluationResult(
            run_id=run.id,
            faithfulness=0.5,
            completeness=0.5,
            retrieval_relevance=0.5,
            context_coverage=0.5,
            failure_type="NO_FAILURE",
            used_llm_judge=True,
            metadata_json={"evaluator_type": "llm"},
            cost_usd=Decimal(str(cost)),
        )
    )
    await session.commit()
    return run.id


def test_run_dynamic_paths_use_starlette_int_converter():
    """Regression: ``/{run_id}`` (str) captures ``dashboard-summary`` → 422; ``:int`` does not."""
    from app.api.runs import router as runs_router

    paths = [getattr(r, "path", "") for r in runs_router.routes if hasattr(r, "path")]
    for suffix in ("/{run_id:int}/requeue", "/{run_id:int}/queue-status", "/{run_id:int}"):
        assert suffix in paths, f"missing Starlette int path segment {suffix!r}, got {paths!r}"


@pytest.mark.asyncio
async def test_int_path_converter_allows_static_runs_segment_after_dynamic():
    """Starlette ``/{id:int}`` does not match ``dashboard-summary``, so static routes stay reachable
    even if registered after the dynamic route (common footgun with plain ``/{run_id}``).
    """
    r = APIRouter()

    @r.get("/{run_id:int}")
    async def _detail(run_id: int) -> dict:
        return {"run_id": run_id}

    @r.get("/dashboard-summary")
    async def _dash() -> dict:
        return {"dash": True}

    app = FastAPI()
    app.include_router(r, prefix="/runs")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        d = await c.get("/runs/dashboard-summary")
        n = await c.get("/runs/42")
    assert d.status_code == 200
    assert d.json() == {"dash": True}
    assert n.status_code == 200
    assert n.json() == {"run_id": 42}


@pytest.mark.asyncio
async def test_dashboard_summary_response_shape(dash_client: AsyncClient):
    """Shared DB may contain rows from other tests; assert contract shape only."""
    resp = await dash_client.get(f"{BASE}/runs/dashboard-summary")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body["total_runs"], int)
    assert "scale" in body
    sc = body["scale"]
    for k in (
        "benchmark_datasets",
        "total_queries",
        "total_traced_runs",
        "configs_tested",
        "documents_processed",
        "chunks_indexed",
    ):
        assert k in sc
        assert isinstance(sc[k], int)
    assert "completed" in body["status_counts"]
    assert "heuristic_runs" in body["evaluator_counts"]
    assert "avg_total_latency_ms" in body["latency"]
    assert "end_to_end_run_latency_avg_sec" in body["latency"]
    assert "end_to_end_run_latency_p95_sec" in body["latency"]
    assert "retrieval_latency_p50_ms" in body["latency"]
    assert "retrieval_latency_p95_ms" in body["latency"]
    assert "evaluation_rows_with_cost" in body["cost"]
    co = body["cost"]
    for k in (
        "avg_cost_usd_per_llm_run",
        "llm_runs_with_measured_cost",
        "avg_cost_usd_per_full_rag_run",
        "full_rag_runs_with_measured_cost",
    ):
        assert k in co
    assert isinstance(co["llm_runs_with_measured_cost"], int)
    assert isinstance(co["full_rag_runs_with_measured_cost"], int)
    assert isinstance(body["failure_type_counts"], dict)
    assert isinstance(body["recent_runs"], list)


@pytest.mark.asyncio
async def test_dashboard_summary_counts_latency_cost_failures(dash_client: AsyncClient):
    b0 = (await dash_client.get(f"{BASE}/runs/dashboard-summary")).json()
    async with async_session_maker() as session:
        await _seed_run_with_eval(session, status=STATUS_COMPLETED, failure_type="UNKNOWN", cost=0.01)
        await _seed_run_with_eval(session, status=STATUS_FAILED, failure_type="RETRIEVAL_MISS", cost=None)
        rid_running = await _seed_run_with_eval(
            session, status=STATUS_RUNNING, failure_type="UNKNOWN", cost=0.02
        )

    resp = await dash_client.get(f"{BASE}/runs/dashboard-summary")
    assert resp.status_code == 200
    b = resp.json()
    assert b["total_runs"] == b0["total_runs"] + 3
    assert b["status_counts"]["completed"] == b0["status_counts"]["completed"] + 1
    assert b["status_counts"]["failed"] == b0["status_counts"]["failed"] + 1
    assert b["status_counts"]["in_progress"] == b0["status_counts"]["in_progress"] + 1
    assert b["evaluator_counts"]["llm_runs"] == b0["evaluator_counts"]["llm_runs"] + 3

    assert b["cost"]["evaluation_rows_with_cost"] == b0["cost"]["evaluation_rows_with_cost"] + 2
    assert b["cost"]["evaluation_rows_cost_not_available"] == b0["cost"]["evaluation_rows_cost_not_available"] + 1

    ft0 = b0["failure_type_counts"]
    ft = b["failure_type_counts"]
    assert ft.get("UNKNOWN", 0) == ft0.get("UNKNOWN", 0) + 2
    assert ft.get("RETRIEVAL_MISS", 0) == ft0.get("RETRIEVAL_MISS", 0) + 1

    recent = b["recent_runs"]
    assert len(recent) >= 3
    assert recent[0]["run_id"] == rid_running
    assert recent[0]["evaluator_type"] == "llm"
    assert recent[0]["cost_usd"] == pytest.approx(0.02)

    # Retrieval mean + percentiles from persisted runs (all three seeds use 10 ms)
    assert b["latency"]["avg_retrieval_latency_ms"] == pytest.approx(10.0)
    assert b["latency"]["retrieval_latency_p50_ms"] == pytest.approx(10.0)
    assert b["latency"]["retrieval_latency_p95_ms"] == pytest.approx(10.0)
    # End-to-end sec fields track ``avg_total_latency_ms`` / 1000 and total p95 / 1000 (same SQL path)
    lat = b["latency"]
    if lat["avg_total_latency_ms"] is None:
        assert lat["end_to_end_run_latency_avg_sec"] is None
        assert lat["end_to_end_run_latency_p95_sec"] is None
    else:
        assert lat["end_to_end_run_latency_avg_sec"] == pytest.approx(lat["avg_total_latency_ms"] / 1000.0)
        assert lat["end_to_end_run_latency_p95_sec"] is not None


@pytest.mark.asyncio
async def test_dashboard_summary_scale_increments_with_traced_run_and_corpus(dash_client: AsyncClient):
    """Scale metrics move up when we add a fully traced run plus processed doc + chunk."""
    b0 = (await dash_client.get(f"{BASE}/runs/dashboard-summary")).json()
    async with async_session_maker() as session:
        await _seed_one_traced_run_with_corpus(session)

    b1 = (await dash_client.get(f"{BASE}/runs/dashboard-summary")).json()
    assert b1["scale"]["benchmark_datasets"] == b0["scale"]["benchmark_datasets"] + 1
    assert b1["scale"]["total_queries"] == b0["scale"]["total_queries"] + 1
    assert b1["scale"]["total_traced_runs"] == b0["scale"]["total_traced_runs"] + 1
    assert b1["scale"]["configs_tested"] == b0["scale"]["configs_tested"] + 1
    assert b1["scale"]["documents_processed"] == b0["scale"]["documents_processed"] + 1
    assert b1["scale"]["chunks_indexed"] == b0["scale"]["chunks_indexed"] + 1


@pytest.mark.asyncio
async def test_dashboard_summary_cost_per_llm_run_excludes_heuristic_bucket(dash_client: AsyncClient):
    """Per-run LLM cost counts only LLM-bucket rows with non-null ``cost_usd``."""
    b0 = (await dash_client.get(f"{BASE}/runs/dashboard-summary")).json()
    async with async_session_maker() as session:
        await _seed_heuristic_run(session, cost=None)
        await _seed_run_with_eval(session, status=STATUS_COMPLETED, failure_type="UNKNOWN", cost=0.07)

    b1 = (await dash_client.get(f"{BASE}/runs/dashboard-summary")).json()
    assert b1["cost"]["llm_runs_with_measured_cost"] == b0["cost"]["llm_runs_with_measured_cost"] + 1
    assert b1["cost"]["evaluation_rows_with_cost"] == b0["cost"]["evaluation_rows_with_cost"] + 1
    # Heuristic row has null cost → N/A row count increases by 1
    assert b1["cost"]["evaluation_rows_cost_not_available"] == b0["cost"][
        "evaluation_rows_cost_not_available"
    ] + 1


@pytest.mark.asyncio
async def test_dashboard_summary_cost_per_full_rag_run(dash_client: AsyncClient):
    """Full RAG average uses runs that have ``generation_results`` and LLM measured cost."""
    b0 = (await dash_client.get(f"{BASE}/runs/dashboard-summary")).json()
    async with async_session_maker() as session:
        await _seed_full_rag_llm_run(session, cost=0.055)

    b1 = (await dash_client.get(f"{BASE}/runs/dashboard-summary")).json()
    n0 = b0["cost"]["full_rag_runs_with_measured_cost"]
    assert b1["cost"]["full_rag_runs_with_measured_cost"] == n0 + 1
    assert b1["cost"]["llm_runs_with_measured_cost"] >= b1["cost"]["full_rag_runs_with_measured_cost"]
    assert b1["cost"]["avg_cost_usd_per_full_rag_run"] is not None
    # With no prior full-RAG measured rows in DB, the single seed fixes the average at 0.055.
    if n0 == 0:
        assert b1["cost"]["avg_cost_usd_per_full_rag_run"] == pytest.approx(0.055, rel=1e-5)


@pytest.mark.asyncio
async def test_dashboard_summary_excludes_benchmark_realism_runs(dash_client: AsyncClient):
    """Runs with ``metadata_json.benchmark_realism`` do not affect summary aggregates."""
    b0 = (await dash_client.get(f"{BASE}/runs/dashboard-summary")).json()
    async with async_session_maker() as session:
        await _seed_run_with_eval(
            session,
            status=STATUS_COMPLETED,
            failure_type="UNKNOWN",
            cost=0.99,
            run_metadata={"benchmark_realism": True},
        )
        await _seed_run_with_eval(
            session,
            status=STATUS_COMPLETED,
            failure_type="NO_FAILURE",
            cost=0.02,
            run_metadata=None,
        )

    b1 = (await dash_client.get(f"{BASE}/runs/dashboard-summary")).json()
    assert b1["total_runs"] == b0["total_runs"] + 1
    assert b1["evaluator_counts"]["llm_runs"] == b0["evaluator_counts"]["llm_runs"] + 1
    assert b1["cost"]["evaluation_rows_with_cost"] == b0["cost"]["evaluation_rows_with_cost"] + 1
    assert b1["failure_type_counts"].get("UNKNOWN", 0) == b0["failure_type_counts"].get("UNKNOWN", 0)
    assert b1["failure_type_counts"].get("NO_FAILURE", 0) == b0["failure_type_counts"].get("NO_FAILURE", 0) + 1


@pytest.mark.asyncio
async def test_dashboard_summary_latency_matches_analytics_excluding_realism(dash_client: AsyncClient):
    """Retrieval latency mean on summary uses the same run scope as dashboard-analytics."""
    sum0 = (await dash_client.get(f"{BASE}/runs/dashboard-summary")).json()
    an0 = (await dash_client.get(f"{BASE}/runs/dashboard-analytics")).json()
    r_sum = sum0["latency"]["avg_retrieval_latency_ms"]
    r_an = an0["latency_distribution"]["retrieval"]["avg_ms"]
    assert (r_sum is None) == (r_an is None), f"summary vs analytics retrieval avg: {r_sum!r} vs {r_an!r}"
    if r_sum is not None:
        assert r_sum == pytest.approx(r_an)

    async with async_session_maker() as session:
        await _seed_run_with_eval(
            session,
            status=STATUS_COMPLETED,
            failure_type="NO_FAILURE",
            cost=None,
            run_metadata={"benchmark_realism": True},
            retrieval_latency_ms=99_999,
            generation_latency_ms=0,
            evaluation_latency_ms=0,
            total_latency_ms=99_999,
        )

    sum1 = (await dash_client.get(f"{BASE}/runs/dashboard-summary")).json()
    an1 = (await dash_client.get(f"{BASE}/runs/dashboard-analytics")).json()
    assert sum1["latency"]["avg_retrieval_latency_ms"] == r_sum
    assert an1["latency_distribution"]["retrieval"]["avg_ms"] == r_an
    r_sum_1 = sum1["latency"]["avg_retrieval_latency_ms"]
    r_an_1 = an1["latency_distribution"]["retrieval"]["avg_ms"]
    assert (r_sum_1 is None) == (r_an_1 is None)
    if r_sum_1 is not None:
        assert r_sum_1 == pytest.approx(r_an_1)
