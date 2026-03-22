"""Full RAG path (retrieval → generation → LLM judge) with mocked Claude."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.database import async_session_maker
from app.domain.failure_taxonomy import FailureType
from app.models import EvaluationResult, GenerationResult, Run
from app.services import trace_persistence as tp
from app.services.benchmark_run import execute_retrieval_benchmark_run
from app.services.full_rag_evaluation import execute_llm_judge_and_complete_run
from app.services.generation_phase import execute_generation_for_run
from app.services.llm_judge_evaluation import LLMJudgeEvalResult
from app.services.rag_generation import GenerationModelResult
from app.services.run_lifecycle import STATUS_COMPLETED, STATUS_GENERATION_COMPLETED
from tests.conftest import make_upload

BASE = "/api/v1"
CORPUS = (
    "Paris is the capital of France. The Eiffel Tower is in Paris. "
    "French cuisine is well known worldwide."
)


@pytest.mark.asyncio
async def test_full_rag_generation_then_llm_judge_persists(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(
        "app.config.settings.anthropic_input_usd_per_million_tokens",
        0.0,
    )
    monkeypatch.setattr(
        "app.config.settings.anthropic_output_usd_per_million_tokens",
        0.0,
    )
    monkeypatch.setattr(
        "app.config.settings.openai_input_usd_per_million_tokens",
        0.0,
    )
    monkeypatch.setattr(
        "app.config.settings.openai_output_usd_per_million_tokens",
        0.0,
    )

    async def fake_gen(*args, **kwargs):
        return GenerationModelResult(
            answer_text="Paris is the capital of France.",
            model_id="fake-gen",
            input_tokens=10,
            output_tokens=12,
            raw_stop_reason="end_turn",
            metadata_json={"test": True},
        )

    async def fake_judge(*args, **kwargs):
        return LLMJudgeEvalResult(
            faithfulness=0.9,
            completeness=0.85,
            groundedness=0.88,
            retrieval_relevance=0.92,
            context_coverage=0.8,
            failure_type=FailureType.NO_FAILURE.value,
            judge_input_tokens=40,
            judge_output_tokens=60,
            metadata_json={"evaluator": "fake_judge", "evaluator_type": "llm"},
        )

    monkeypatch.setattr(
        "app.services.generation_phase.generate_rag_answer",
        fake_gen,
    )
    # ``full_rag_evaluation`` binds the judge at import time — patch that reference.
    monkeypatch.setattr(
        "app.services.full_rag_evaluation.evaluate_with_llm_judge",
        fake_judge,
    )

    async with async_session_maker() as session:
        ds = await tp.create_dataset(session, name="full_rag_ds", description="")
        qc = await tp.create_query_case(
            session,
            dataset_id=ds.id,
            query_text="What is the capital of France?",
            expected_answer="Paris",
        )
        pc = await tp.create_pipeline_config(
            session,
            name="full_rag_pc",
            embedding_model="all-MiniLM-L6-v2",
            chunk_strategy="fixed",
            chunk_size=120,
            chunk_overlap=0,
            top_k=5,
        )
        await session.commit()
        qid, pid = qc.id, pc.id

    up = await client.post(
        f"{BASE}/documents",
        params={"chunk_size": 100},
        files=make_upload("corpus.txt", CORPUS),
    )
    assert up.status_code == 201

    async with async_session_maker() as session:
        run = await execute_retrieval_benchmark_run(
            session,
            query_case_id=qid,
            pipeline_config_id=pid,
            commit=True,
        )
        rid = run.id

    async with async_session_maker() as session:
        gr = await execute_generation_for_run(session, run_id=rid, commit=True)
        assert gr.answer_text.startswith("Paris")

    async with async_session_maker() as session:
        r = await session.get(Run, rid)
        assert r is not None
        assert r.status == STATUS_GENERATION_COMPLETED
        assert r.generation_latency_ms is not None

    async with async_session_maker() as session:
        await execute_llm_judge_and_complete_run(session, run_id=rid, commit=True)

    async with async_session_maker() as session:
        r = await session.get(Run, rid)
        assert r is not None
        assert r.status == STATUS_COMPLETED
        assert r.evaluation_latency_ms is not None
        assert r.total_latency_ms is not None

        gen_row = (
            await session.execute(select(GenerationResult).where(GenerationResult.run_id == rid))
        ).scalar_one()
        assert "Paris" in gen_row.answer_text

        er = (
            await session.execute(select(EvaluationResult).where(EvaluationResult.run_id == rid))
        ).scalar_one()
        assert er.used_llm_judge is True
        assert er.faithfulness == pytest.approx(0.9)
        assert er.groundedness == pytest.approx(0.88)
        assert er.failure_type == FailureType.NO_FAILURE.value
        assert er.metadata_json is not None
        assert er.metadata_json.get("evaluator_type") == "llm"
