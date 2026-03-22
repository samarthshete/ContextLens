"""GET /api/v1/runs/dashboard-analytics — response shape and correctness."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.database import async_session_maker
from app.main import app
from app.models import Dataset, EvaluationResult, PipelineConfig, QueryCase, Run
from app.services.run_lifecycle import STATUS_COMPLETED, STATUS_FAILED

BASE = "/api/v1"


@pytest.fixture
async def analytics_client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def _seed(session, *, status: str, failure_type: str, cost: float | None, latency: int = 60):
    ds = Dataset(name="analytics_ds", description="")
    session.add(ds)
    await session.flush()
    qc = QueryCase(dataset_id=ds.id, query_text="q?", expected_answer=None)
    pc = PipelineConfig(
        name="analytics_pc",
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
        total_latency_ms=latency,
    )
    session.add(run)
    await session.flush()
    session.add(
        EvaluationResult(
            run_id=run.id,
            faithfulness=0.8,
            completeness=0.7,
            retrieval_relevance=0.9,
            context_coverage=0.6,
            failure_type=failure_type,
            used_llm_judge=True,
            metadata_json={"evaluator_type": "llm"},
            cost_usd=cost,
        )
    )
    await session.commit()
    return run.id


@pytest.mark.asyncio
async def test_analytics_response_shape(analytics_client: AsyncClient):
    """Assert the analytics endpoint returns all four sections with correct structure."""
    resp = await analytics_client.get(f"{BASE}/runs/dashboard-analytics")
    assert resp.status_code == 200
    body = resp.json()

    # Top-level sections exist
    assert "time_series" in body
    assert "latency_distribution" in body
    assert "end_to_end_run_latency_avg_sec" in body
    assert "end_to_end_run_latency_p95_sec" in body
    assert "failure_analysis" in body
    assert "config_insights" in body

    # time_series is a list
    assert isinstance(body["time_series"], list)

    # latency_distribution has all phases
    ld = body["latency_distribution"]
    for phase in ("retrieval", "generation", "evaluation", "total"):
        assert phase in ld
        phase_data = ld[phase]
        assert "count" in phase_data
        assert "min_ms" in phase_data
        assert "max_ms" in phase_data
        assert "avg_ms" in phase_data
        assert "median_ms" in phase_data
        assert "p95_ms" in phase_data

    # failure_analysis structure
    fa = body["failure_analysis"]
    assert "overall_counts" in fa
    assert "overall_percentages" in fa
    assert "by_config" in fa
    assert "recent_failed_runs" in fa

    # config_insights is a list
    assert isinstance(body["config_insights"], list)


@pytest.mark.asyncio
async def test_analytics_with_seeded_data(analytics_client: AsyncClient):
    """Seed runs and verify analytics reflects them."""
    async with async_session_maker() as session:
        await _seed(session, status=STATUS_COMPLETED, failure_type="RETRIEVAL_MISS", cost=0.01, latency=50)
        await _seed(session, status=STATUS_COMPLETED, failure_type="UNKNOWN", cost=0.02, latency=100)
        await _seed(session, status=STATUS_FAILED, failure_type="RETRIEVAL_MISS", cost=None, latency=200)

    resp = await analytics_client.get(f"{BASE}/runs/dashboard-analytics")
    assert resp.status_code == 200
    body = resp.json()

    # time_series should have at least one day
    assert len(body["time_series"]) >= 1

    # latency_distribution total should have data
    total = body["latency_distribution"]["total"]
    assert total["count"] >= 3
    assert total["min_ms"] is not None
    assert total["max_ms"] is not None
    assert total["avg_ms"] is not None
    assert total["median_ms"] is not None
    assert total["p95_ms"] is not None
    # End-to-end sec metrics match ``latency_distribution.total`` / 1000 (same SQL population)
    assert body["end_to_end_run_latency_avg_sec"] == pytest.approx(total["avg_ms"] / 1000.0)
    assert body["end_to_end_run_latency_p95_sec"] == pytest.approx(total["p95_ms"] / 1000.0)

    # failure_analysis should include RETRIEVAL_MISS
    fa = body["failure_analysis"]
    assert fa["overall_counts"].get("RETRIEVAL_MISS", 0) >= 2
    assert "RETRIEVAL_MISS" in fa["overall_percentages"]

    # config_insights should have entries
    assert len(body["config_insights"]) >= 1
    ci = body["config_insights"][0]
    assert "pipeline_config_id" in ci
    assert "pipeline_config_name" in ci
    assert "traced_runs" in ci
    assert "avg_retrieval_relevance" in ci
    assert "avg_faithfulness" in ci


@pytest.mark.asyncio
async def test_analytics_endpoint_does_not_break_dashboard_summary(analytics_client: AsyncClient):
    """Ensure the existing dashboard-summary endpoint still works after adding analytics."""
    resp = await analytics_client.get(f"{BASE}/runs/dashboard-summary")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body["total_runs"], int)
