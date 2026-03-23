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
    ci = body["config_insights"]
    assert isinstance(ci, dict)
    assert "heuristic" in ci and "llm" in ci
    assert isinstance(ci["heuristic"], list)
    assert isinstance(ci["llm"], list)

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

    # config_insights.llm should have entries (seeded rows are LLM bucket)
    llm_insights = body["config_insights"]["llm"]
    assert len(llm_insights) >= 1
    ci = llm_insights[0]
    assert "pipeline_config_id" in ci
    assert "pipeline_config_name" in ci
    assert "traced_runs" in ci
    assert "avg_retrieval_relevance" in ci
    assert "avg_faithfulness" in ci


@pytest.mark.asyncio
async def test_time_series_cost_is_per_run_average(analytics_client: AsyncClient):
    """avg_cost_usd in time_series is the mean of per-run costs, not per-eval-row.

    Seeds two runs on the same day with costs 0.10 and 0.30.  The expected
    daily average is 0.20.  If cost were naively averaged over joined eval rows
    (e.g. after a one-to-many join), the number could differ.
    """
    async with async_session_maker() as session:
        await _seed(session, status=STATUS_COMPLETED, failure_type="NO_FAILURE", cost=0.10, latency=50)
        await _seed(session, status=STATUS_COMPLETED, failure_type="NO_FAILURE", cost=0.30, latency=80)

    resp = await analytics_client.get(f"{BASE}/runs/dashboard-analytics")
    assert resp.status_code == 200
    ts = resp.json()["time_series"]
    assert len(ts) >= 1

    # Find today's bucket (seeds all land on the same day)
    today_bucket = ts[-1]  # newest is last (reversed to oldest-first)
    assert today_bucket["avg_cost_usd"] == pytest.approx(0.20, abs=1e-6)


@pytest.mark.asyncio
async def test_time_series_null_cost_excluded_zero_cost_preserved(analytics_client: AsyncClient):
    """NULL cost rows are excluded; zero cost is a measured value and preserved."""
    async with async_session_maker() as session:
        await _seed(session, status=STATUS_COMPLETED, failure_type="NO_FAILURE", cost=None, latency=40)
        await _seed(session, status=STATUS_COMPLETED, failure_type="NO_FAILURE", cost=0.0, latency=60)
        await _seed(session, status=STATUS_COMPLETED, failure_type="NO_FAILURE", cost=0.20, latency=70)

    resp = await analytics_client.get(f"{BASE}/runs/dashboard-analytics")
    assert resp.status_code == 200
    ts = resp.json()["time_series"]
    assert len(ts) >= 1

    today_bucket = ts[-1]
    # Only 2 runs have measured cost (0.0 and 0.20) → avg = 0.10
    assert today_bucket["avg_cost_usd"] == pytest.approx(0.10, abs=1e-6)


@pytest.mark.asyncio
async def test_time_series_all_null_cost_returns_null(analytics_client: AsyncClient):
    """When all runs on a day have NULL cost, avg_cost_usd is null."""
    async with async_session_maker() as session:
        await _seed(session, status=STATUS_COMPLETED, failure_type="NO_FAILURE", cost=None, latency=50)

    resp = await analytics_client.get(f"{BASE}/runs/dashboard-analytics")
    assert resp.status_code == 200
    ts = resp.json()["time_series"]
    assert len(ts) >= 1

    today_bucket = ts[-1]
    assert today_bucket["avg_cost_usd"] is None


async def _seed_with_config(
    session,
    *,
    config_name: str,
    cost: float | None,
    latency: int = 60,
    status: str = STATUS_COMPLETED,
    failure_type: str = "NO_FAILURE",
):
    """Seed a run under a named pipeline config.  Returns (run_id, pc_id)."""
    ds = Dataset(name="ci_ds", description="")
    session.add(ds)
    await session.flush()
    qc = QueryCase(dataset_id=ds.id, query_text="q?", expected_answer=None)
    pc = PipelineConfig(
        name=config_name,
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
    return run.id, pc.id


@pytest.mark.asyncio
async def test_config_insights_avg_cost_is_per_run(analytics_client: AsyncClient):
    """avg_cost_usd in config_insights is the mean of per-run costs.

    Seeds two runs under the same config with costs 0.10 and 0.30.
    The expected avg_cost_usd is 0.20 and total_cost_usd is 0.40.
    """
    async with async_session_maker() as session:
        _, pc_id = await _seed_with_config(session, config_name="ci_cost_avg", cost=0.10)
    async with async_session_maker() as session:
        # Second run under a *different* PipelineConfig row (same name pattern)
        # but we need them under the SAME config.  Re-use pc_id directly.
        ds = Dataset(name="ci_ds2", description="")
        session.add(ds)
        await session.flush()
        qc = QueryCase(dataset_id=ds.id, query_text="q2?", expected_answer=None)
        session.add(qc)
        await session.flush()
        run = Run(
            query_case_id=qc.id,
            pipeline_config_id=pc_id,
            status=STATUS_COMPLETED,
            retrieval_latency_ms=10,
            generation_latency_ms=20,
            evaluation_latency_ms=30,
            total_latency_ms=80,
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
                failure_type="NO_FAILURE",
                used_llm_judge=True,
                metadata_json={"evaluator_type": "llm"},
                cost_usd=0.30,
            )
        )
        await session.commit()

    resp = await analytics_client.get(f"{BASE}/runs/dashboard-analytics")
    assert resp.status_code == 200
    ci_list = resp.json()["config_insights"]["llm"]
    # Find our config
    ci = next(c for c in ci_list if c["pipeline_config_id"] == pc_id)
    assert ci["avg_cost_usd"] == pytest.approx(0.20, abs=1e-6)
    assert ci["total_cost_usd"] == pytest.approx(0.40, abs=1e-6)
    # Non-cost fields should still be populated
    assert ci["traced_runs"] == 2
    assert ci["avg_faithfulness"] == pytest.approx(0.8, abs=1e-6)


@pytest.mark.asyncio
async def test_config_insights_null_cost_excluded_zero_preserved(analytics_client: AsyncClient):
    """NULL cost runs excluded from avg/total; zero cost preserved as measured."""
    async with async_session_maker() as session:
        _, pc_id = await _seed_with_config(session, config_name="ci_null_zero", cost=None)
    async with async_session_maker() as session:
        ds = Dataset(name="ci_nz2", description="")
        session.add(ds)
        await session.flush()
        qc = QueryCase(dataset_id=ds.id, query_text="q?", expected_answer=None)
        session.add(qc)
        await session.flush()
        run = Run(
            query_case_id=qc.id,
            pipeline_config_id=pc_id,
            status=STATUS_COMPLETED,
            retrieval_latency_ms=10,
            total_latency_ms=60,
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
                failure_type="NO_FAILURE",
                used_llm_judge=True,
                metadata_json={"evaluator_type": "llm"},
                cost_usd=0.0,
            )
        )
        await session.commit()
    async with async_session_maker() as session:
        ds = Dataset(name="ci_nz3", description="")
        session.add(ds)
        await session.flush()
        qc = QueryCase(dataset_id=ds.id, query_text="q?", expected_answer=None)
        session.add(qc)
        await session.flush()
        run = Run(
            query_case_id=qc.id,
            pipeline_config_id=pc_id,
            status=STATUS_COMPLETED,
            retrieval_latency_ms=10,
            total_latency_ms=60,
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
                failure_type="NO_FAILURE",
                used_llm_judge=True,
                metadata_json={"evaluator_type": "llm"},
                cost_usd=0.20,
            )
        )
        await session.commit()

    resp = await analytics_client.get(f"{BASE}/runs/dashboard-analytics")
    assert resp.status_code == 200
    ci = next(c for c in resp.json()["config_insights"]["llm"] if c["pipeline_config_id"] == pc_id)
    # 3 runs: NULL, 0.0, 0.20 → avg of measured = (0.0 + 0.20) / 2 = 0.10
    assert ci["avg_cost_usd"] == pytest.approx(0.10, abs=1e-6)
    assert ci["total_cost_usd"] == pytest.approx(0.20, abs=1e-6)
    assert ci["traced_runs"] == 3


@pytest.mark.asyncio
async def test_config_insights_all_null_cost_returns_null(analytics_client: AsyncClient):
    """When all runs under a config have NULL cost, avg/total are null."""
    async with async_session_maker() as session:
        _, pc_id = await _seed_with_config(session, config_name="ci_all_null", cost=None)

    resp = await analytics_client.get(f"{BASE}/runs/dashboard-analytics")
    assert resp.status_code == 200
    ci = next(c for c in resp.json()["config_insights"]["llm"] if c["pipeline_config_id"] == pc_id)
    assert ci["avg_cost_usd"] is None
    assert ci["total_cost_usd"] is None
    assert ci["traced_runs"] == 1


@pytest.mark.asyncio
async def test_analytics_endpoint_does_not_break_dashboard_summary(analytics_client: AsyncClient):
    """Ensure the existing dashboard-summary endpoint still works after adding analytics."""
    resp = await analytics_client.get(f"{BASE}/runs/dashboard-summary")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body["total_runs"], int)


async def _seed_run_with_eval(
    session,
    *,
    pc: PipelineConfig,
    completeness: float,
    used_llm_judge: bool,
    evaluator_type: str | None,
    cost: float | None = None,
):
    ds = Dataset(name="mix_ds", description="")
    session.add(ds)
    await session.flush()
    qc = QueryCase(dataset_id=ds.id, query_text="mix?", expected_answer=None)
    session.add(qc)
    await session.flush()
    run = Run(
        query_case_id=qc.id,
        pipeline_config_id=pc.id,
        status=STATUS_COMPLETED,
        retrieval_latency_ms=10,
        generation_latency_ms=20,
        evaluation_latency_ms=30,
        total_latency_ms=60,
    )
    session.add(run)
    await session.flush()
    meta = {"evaluator_type": evaluator_type} if evaluator_type else {}
    session.add(
        EvaluationResult(
            run_id=run.id,
            faithfulness=0.5,
            completeness=completeness,
            retrieval_relevance=0.5,
            context_coverage=0.5,
            failure_type="NO_FAILURE",
            used_llm_judge=used_llm_judge,
            metadata_json=meta or None,
            cost_usd=cost,
        )
    )
    await session.commit()


@pytest.mark.asyncio
async def test_config_insights_separate_evaluator_buckets_no_blended_scores(analytics_client: AsyncClient):
    """Heuristic and LLM config_insights average scores only within each bucket."""
    async with async_session_maker() as session:
        pc = PipelineConfig(
            name="mix_pc",
            embedding_model="all-MiniLM-L6-v2",
            chunk_strategy="fixed",
            chunk_size=100,
            chunk_overlap=0,
            top_k=3,
        )
        session.add(pc)
        await session.commit()
        await session.refresh(pc)

    async with async_session_maker() as session:
        r_pc = await session.get(PipelineConfig, pc.id)
        assert r_pc is not None
        await _seed_run_with_eval(
            session,
            pc=r_pc,
            completeness=0.10,
            used_llm_judge=False,
            evaluator_type="heuristic",
        )
    async with async_session_maker() as session:
        r_pc = await session.get(PipelineConfig, pc.id)
        assert r_pc is not None
        await _seed_run_with_eval(
            session,
            pc=r_pc,
            completeness=0.90,
            used_llm_judge=True,
            evaluator_type="llm",
            cost=0.05,
        )

    resp = await analytics_client.get(f"{BASE}/runs/dashboard-analytics")
    assert resp.status_code == 200
    buckets = resp.json()["config_insights"]
    h = next(c for c in buckets["heuristic"] if c["pipeline_config_id"] == pc.id)
    l = next(c for c in buckets["llm"] if c["pipeline_config_id"] == pc.id)
    assert h["traced_runs"] == 1
    assert h["avg_completeness"] == pytest.approx(0.10, abs=1e-6)
    assert l["traced_runs"] == 1
    assert l["avg_completeness"] == pytest.approx(0.90, abs=1e-6)
    # Blended average would be 0.50 — neither bucket should show that
    assert h["avg_completeness"] != pytest.approx(0.50, abs=1e-3)
    assert l["avg_completeness"] != pytest.approx(0.50, abs=1e-3)
