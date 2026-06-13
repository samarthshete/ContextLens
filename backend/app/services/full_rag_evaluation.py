"""LLM judge evaluation after generation (completes run)."""

from __future__ import annotations

import time
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Chunk, GenerationResult, QueryCase, RetrievalResult, Run
from app.services.cost_estimation import estimate_usd_from_tokens
from app.services.evaluation_persistence import persist_evaluation_and_complete_run
from app.services.llm_judge_evaluation import evaluate_with_llm_judge
from app.services.minimal_retrieval_evaluation import (
    compute_hybrid_skipped_evaluation,
    compute_minimal_retrieval_evaluation,
    hybrid_retrieval_gate_passes,
)
from app.services.run_lifecycle import STATUS_GENERATION_COMPLETED
from app.services.trace_instrumentation import (
    full_llm_run_instrumentation,
    hybrid_skipped_judge_instrumentation,
    merge_run_trace_instrumentation,
)


def _evaluator_mode_from_run_metadata(meta: dict | None) -> str:
    if not meta:
        return "llm_only"
    return str(meta.get("evaluator_execution_mode") or "llm_only")


async def execute_llm_judge_and_complete_run(
    session: AsyncSession,
    *,
    run_id: int,
    commit: bool = True,
) -> None:
    """Run LLM judge on stored generation + context; persist evaluation + ``completed``.

    Expects ``status == generation_completed`` and no ``evaluation_results`` row yet.
    ``total_latency_ms`` = sum of measured retrieval + generation + evaluation phase ms on the run.
    ``cost_usd`` = sum of **generation** + **judge** USD estimates from
    ``estimate_usd_from_tokens`` (rates follow ``LLM_PROVIDER``: OpenAI vs Anthropic fields in config).
    If **pricing is disabled** (both input and output rates ≤ 0), both estimates are
    ``None`` and ``cost_usd`` stays **null** (never written as a fake ``0``).
    If only one side returns a value, the other is treated as ``0`` in the sum (partial
    visibility). A **true zero** bill (e.g. zero reported tokens with rates on) is stored
    as ``0``, not coerced to null.
    """
    run = await session.get(Run, run_id)
    if run is None:
        raise ValueError(f"Run id={run_id} not found")
    if run.status != STATUS_GENERATION_COMPLETED:
        raise ValueError(
            f"Run id={run_id} must have status {STATUS_GENERATION_COMPLETED!r}, got {run.status!r}"
        )

    gen = (
        await session.execute(select(GenerationResult).where(GenerationResult.run_id == run_id))
    ).scalar_one_or_none()
    if gen is None:
        raise ValueError(f"No generation_results for run id={run_id}")

    qc = await session.get(QueryCase, run.query_case_id)
    if qc is None:
        raise ValueError("Query case missing")

    stmt = (
        select(RetrievalResult, Chunk.content)
        .join(Chunk, Chunk.id == RetrievalResult.chunk_id)
        .where(RetrievalResult.run_id == run_id)
        .order_by(RetrievalResult.rank)
    )
    rows = (await session.execute(stmt)).all()
    bodies = [content for _, content in rows]
    scores = [float(rr.score) for rr, _ in rows]
    max_chunk_score = max(scores) if scores else 0.0

    mode = _evaluator_mode_from_run_metadata(run.metadata_json)
    use_hybrid = mode == "hybrid"

    retrieval_ms = run.retrieval_latency_ms or 0
    generation_ms = run.generation_latency_ms or 0
    gen_cost = estimate_usd_from_tokens(gen.input_tokens, gen.output_tokens)

    if use_hybrid:
        pre = await compute_minimal_retrieval_evaluation(session, run_id=run_id)
        gate_ok = hybrid_retrieval_gate_passes(
            max_chunk_score=max_chunk_score,
            retrieval_relevance=pre.retrieval_relevance,
            context_coverage=pre.context_coverage,
        )
    else:
        gate_ok = False

    if use_hybrid and gate_ok:
        t0 = time.perf_counter()
        ev_h = await compute_hybrid_skipped_evaluation(
            session,
            run_id=run_id,
            generated_answer=gen.answer_text,
        )
        eval_ms = max(0, int((time.perf_counter() - t0) * 1000))
        total_ms = retrieval_ms + generation_ms + eval_ms
        cost_usd = gen_cost

        meta = dict(ev_h.metadata_json)
        meta["generation_model"] = gen.model_id
        meta["generation_input_tokens"] = gen.input_tokens
        meta["generation_output_tokens"] = gen.output_tokens

        await persist_evaluation_and_complete_run(
            session,
            run_id=run_id,
            evaluation_latency_ms=eval_ms,
            total_latency_ms=total_ms,
            faithfulness=ev_h.faithfulness,
            completeness=ev_h.completeness,
            retrieval_relevance=ev_h.retrieval_relevance,
            context_coverage=ev_h.context_coverage,
            groundedness=None,
            failure_type=ev_h.failure_type,
            used_llm_judge=False,
            cost_usd=cost_usd,
            metadata_json=meta,
            prerequisite_status=STATUS_GENERATION_COMPLETED,
            commit=False,
        )
        await merge_run_trace_instrumentation(
            session,
            run_id=run_id,
            patch=hybrid_skipped_judge_instrumentation(
                gen_input_tokens=gen.input_tokens,
                gen_output_tokens=gen.output_tokens,
                gen_cost_component=gen_cost,
            ),
        )
    else:
        t0 = time.perf_counter()
        ev = await evaluate_with_llm_judge(
            query=qc.query_text,
            context_chunks=bodies,
            generated_answer=gen.answer_text,
            reference_answer=qc.expected_answer,
        )
        eval_ms = max(0, int((time.perf_counter() - t0) * 1000))

        total_ms = retrieval_ms + generation_ms + eval_ms

        judge_cost = estimate_usd_from_tokens(ev.judge_input_tokens, ev.judge_output_tokens)
        cost_usd: Decimal | None = None
        if gen_cost is not None or judge_cost is not None:
            cost_usd = (gen_cost or Decimal("0")) + (judge_cost or Decimal("0"))

        meta = dict(ev.metadata_json)
        meta["generation_model"] = gen.model_id
        meta["generation_input_tokens"] = gen.input_tokens
        meta["generation_output_tokens"] = gen.output_tokens
        if use_hybrid and not gate_ok:
            meta["hybrid_judge_gate_failed"] = True
            meta["hybrid_gate_max_chunk_score"] = max_chunk_score

        await persist_evaluation_and_complete_run(
            session,
            run_id=run_id,
            evaluation_latency_ms=eval_ms,
            total_latency_ms=total_ms,
            faithfulness=ev.faithfulness,
            completeness=ev.completeness,
            retrieval_relevance=ev.retrieval_relevance,
            context_coverage=ev.context_coverage,
            groundedness=ev.groundedness,
            failure_type=ev.failure_type,
            used_llm_judge=True,
            cost_usd=cost_usd,
            metadata_json=meta,
            prerequisite_status=STATUS_GENERATION_COMPLETED,
            commit=False,
        )
        await merge_run_trace_instrumentation(
            session,
            run_id=run_id,
            patch=full_llm_run_instrumentation(
                judge_input_tokens=ev.judge_input_tokens,
                judge_output_tokens=ev.judge_output_tokens,
                gen_input_tokens=gen.input_tokens,
                gen_output_tokens=gen.output_tokens,
                cost_usd=cost_usd,
            ),
        )

    if commit:
        await session.commit()
