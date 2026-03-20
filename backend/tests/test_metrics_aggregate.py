"""Metrics aggregation from seeded DB rows (deterministic checks, no fake benchmark claims)."""

from decimal import Decimal

import pytest

from app.database import async_session_maker, engine
from app.metrics.aggregate import aggregate_all_metrics
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


@pytest.mark.asyncio
async def test_aggregate_metrics_matches_seeded_latencies_and_counts():
    """Two fully traced runs (one heuristic, one LLM) → split averages, not blended."""
    async with async_session_maker() as session:
        ds = Dataset(name="seed_ds", description="")
        session.add(ds)
        await session.flush()

        qc = QueryCase(
            dataset_id=ds.id,
            query_text="q1",
            metadata_json={},
        )
        pc = PipelineConfig(
            name="seed_pc",
            embedding_model="all-MiniLM-L6-v2",
            chunk_strategy="fixed",
            chunk_size=100,
            chunk_overlap=0,
            top_k=3,
        )
        session.add_all([qc, pc])
        await session.flush()

        doc = Document(
            title="seed.txt",
            source_type="txt",
            file_path="seed://metrics_test",
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

        r1 = Run(
            query_case_id=qc.id,
            pipeline_config_id=pc.id,
            status=STATUS_COMPLETED,
            retrieval_latency_ms=100,
            evaluation_latency_ms=50,
            total_latency_ms=150,
        )
        r2 = Run(
            query_case_id=qc.id,
            pipeline_config_id=pc.id,
            status=STATUS_COMPLETED,
            retrieval_latency_ms=300,
            evaluation_latency_ms=50,
            total_latency_ms=350,
        )
        session.add_all([r1, r2])
        await session.flush()

        session.add_all(
            [
                RetrievalResult(run_id=r1.id, chunk_id=ch.id, rank=1, score=0.9),
                RetrievalResult(run_id=r2.id, chunk_id=ch.id, rank=1, score=0.8),
            ]
        )
        session.add_all(
            [
                EvaluationResult(
                    run_id=r1.id,
                    faithfulness=0.8,
                    completeness=0.7,
                    retrieval_relevance=0.6,
                    context_coverage=0.5,
                    failure_type="NO_FAILURE",
                    used_llm_judge=False,
                    metadata_json={"evaluator_type": "heuristic"},
                    cost_usd=Decimal("0.02"),
                ),
                EvaluationResult(
                    run_id=r2.id,
                    faithfulness=0.4,
                    completeness=0.3,
                    retrieval_relevance=0.2,
                    context_coverage=0.1,
                    failure_type="UNKNOWN",
                    used_llm_judge=True,
                    metadata_json={"evaluator_type": "llm"},
                    cost_usd=Decimal("0.04"),
                ),
            ]
        )
        await session.commit()

    async with engine.connect() as conn:
        m = await aggregate_all_metrics(conn)

    assert m.get("_missing_tables") is None
    assert m["benchmark_datasets"] == 1
    assert m["total_queries"] == 1
    assert m["configs_tested"] == 1
    assert m["total_traced_runs"] == 2
    assert m["total_traced_runs_heuristic"] == 1
    assert m["total_traced_runs_llm"] == 1
    assert m["evaluation_rows_heuristic"] == 1
    assert m["evaluation_rows_llm"] == 1

    assert m["avg_retrieval_latency_ms"] == pytest.approx(200.0)
    assert m["avg_evaluation_latency_ms"] == pytest.approx(50.0)
    assert m["avg_total_latency_ms"] == pytest.approx(250.0)

    assert m["avg_faithfulness_heuristic"] == pytest.approx(0.8)
    assert m["avg_faithfulness_llm"] == pytest.approx(0.4)
    assert m.get("avg_faithfulness") is None

    assert m["failure_type_counts_heuristic"]["NO_FAILURE"] == 1
    assert m["failure_type_counts_llm"]["UNKNOWN"] == 1
    assert m["failure_type_counts_all"]["NO_FAILURE"] == 1
    assert m["failure_type_counts_all"]["UNKNOWN"] == 1

    assert float(m["avg_evaluation_cost_per_run_usd_heuristic"]) == pytest.approx(0.02)
    assert float(m["avg_evaluation_cost_per_run_usd_llm"]) == pytest.approx(0.04)
    assert m["llm_judge_call_rate"] == pytest.approx(0.5)

    assert m["p95_retrieval_latency_ms"] is not None
    assert 100 <= m["p95_retrieval_latency_ms"] <= 300
