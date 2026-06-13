"""Merge persisted counters on ``runs.trace_instrumentation_json`` (evaluation / LLM usage)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Run

EvaluatorExecutionMode = Literal["heuristic_only", "llm_only", "hybrid"]


async def merge_run_trace_instrumentation(
    session: AsyncSession,
    *,
    run_id: int,
    patch: dict[str, Any],
    commit: bool = False,
) -> None:
    """JSON-merge *patch* onto ``Run.trace_instrumentation_json`` (shallow keys)."""
    run = await session.get(Run, run_id)
    if run is None:
        return
    base = dict(run.trace_instrumentation_json or {})
    base.update(patch)
    run.trace_instrumentation_json = base
    await session.flush()
    if commit:
        await session.commit()


def heuristic_run_instrumentation() -> dict[str, Any]:
    return {
        "evaluator_execution_mode": "heuristic_only",
        "total_eval_rows": 1,
        "heuristic_eval_rows": 1,
        "llm_eval_rows": 0,
        "llm_generation_calls": 0,
        "llm_judge_calls_attempted": 0,
        "llm_judge_calls_skipped_by_heuristics": 0,
        "llm_judge_calls_used_for_final_judgment": 0,
        "estimated_prompt_tokens": None,
        "estimated_completion_tokens": None,
        "estimated_cost_usd": None,
    }


def full_llm_run_instrumentation(
    *,
    judge_input_tokens: int | None,
    judge_output_tokens: int | None,
    gen_input_tokens: int | None,
    gen_output_tokens: int | None,
    cost_usd: Decimal | None,
) -> dict[str, Any]:
    est_in = _sum_tokens(gen_input_tokens, judge_input_tokens)
    est_out = _sum_tokens(gen_output_tokens, judge_output_tokens)
    return {
        "evaluator_execution_mode": "llm_only",
        "total_eval_rows": 1,
        "heuristic_eval_rows": 0,
        "llm_eval_rows": 1,
        "llm_generation_calls": 1,
        "llm_judge_calls_attempted": 1,
        "llm_judge_calls_skipped_by_heuristics": 0,
        "llm_judge_calls_used_for_final_judgment": 1,
        "estimated_prompt_tokens": est_in,
        "estimated_completion_tokens": est_out,
        "estimated_cost_usd": float(cost_usd) if cost_usd is not None else None,
    }


def hybrid_skipped_judge_instrumentation(
    *,
    gen_input_tokens: int | None,
    gen_output_tokens: int | None,
    gen_cost_component: Decimal | None,
) -> dict[str, Any]:
    est_in = gen_input_tokens
    est_out = gen_output_tokens
    return {
        "evaluator_execution_mode": "hybrid",
        "total_eval_rows": 1,
        "heuristic_eval_rows": 1,
        "llm_eval_rows": 0,
        "llm_generation_calls": 1,
        "llm_judge_calls_attempted": 1,
        "llm_judge_calls_skipped_by_heuristics": 1,
        "llm_judge_calls_used_for_final_judgment": 0,
        "estimated_prompt_tokens": est_in,
        "estimated_completion_tokens": est_out,
        "estimated_cost_usd": float(gen_cost_component) if gen_cost_component is not None else None,
    }


def _sum_tokens(*parts: int | None) -> int | None:
    vals = [p for p in parts if p is not None]
    if not vals:
        return None
    return sum(vals)
