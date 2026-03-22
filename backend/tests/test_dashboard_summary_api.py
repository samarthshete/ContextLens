"""GET /api/v1/runs/dashboard-summary."""

import pytest
from fastapi import APIRouter, FastAPI
from httpx import ASGITransport, AsyncClient

from app.database import async_session_maker
from app.main import app
from app.models import Dataset, EvaluationResult, PipelineConfig, QueryCase, Run
from app.services.run_lifecycle import STATUS_COMPLETED, STATUS_FAILED, STATUS_RUNNING

BASE = "/api/v1"


@pytest.fixture
async def dash_client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def _seed_run_with_eval(session, *, status: str, failure_type: str, cost: float | None):
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
        retrieval_latency_ms=10,
        generation_latency_ms=20,
        evaluation_latency_ms=30,
        total_latency_ms=60,
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
    assert "completed" in body["status_counts"]
    assert "heuristic_runs" in body["evaluator_counts"]
    assert "avg_total_latency_ms" in body["latency"]
    assert "evaluation_rows_with_cost" in body["cost"]
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
