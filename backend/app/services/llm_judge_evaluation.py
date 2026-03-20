"""LLM-as-judge: scores + failure taxonomy from Claude (JSON output)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.config import settings
from app.domain.failure_taxonomy import FailureType
from app.services.anthropic_client import get_async_anthropic
from app.services.llm_judge_parse import extract_judge_json_object, parse_judge_payload

# Logical evaluator id (bucket / metadata.evaluator); unchanged for backward compatibility.
EVALUATOR_ID = "claude_llm_judge_v1"
# Prompt + parsing contract version (persisted on every judge evaluation).
JUDGE_PROMPT_VERSION = "claude_llm_judge_v2"

_FAILURE_ENUM_LINE = ", ".join(f'"{m.value}"' for m in FailureType)

JUDGE_SYSTEM = f"""You are an evaluation judge for a RAG system.
Respond with ONLY a single JSON object (no markdown outside the JSON) using these keys:
- faithfulness: number 0-1 (is the answer supported by the context?)
- completeness: number 0-1 (does the answer cover what the question asks?)
- groundedness: number 0-1 (does the answer stick to context, avoiding hallucinations?)
- retrieval_relevance: number 0-1 (is the provided context relevant to the question?)
- context_coverage: number 0-1 (does the context contain enough to answer well?)
- failure_type: one of [{_FAILURE_ENUM_LINE}]

Use NO_FAILURE when there is no significant issue. Choose the single best failure label otherwise.
Scores are subjective but must be numeric between 0 and 1."""


def _build_judge_user_payload(
    *,
    query: str,
    context_chunks: list[str],
    generated_answer: str,
    reference_answer: str | None,
) -> str:
    ctx = "\n\n".join(f"[{i+1}] {c}" for i, c in enumerate(context_chunks))
    ref = reference_answer or "(none provided)"
    return f"""### Retrieved context
{ctx}

### User question
{query}

### Generated answer (to evaluate)
{generated_answer}

### Reference answer (optional gold; may be empty)
{ref}

Output only the JSON object."""


@dataclass(frozen=True, slots=True)
class LLMJudgeEvalResult:
    faithfulness: float | None
    completeness: float | None
    groundedness: float | None
    retrieval_relevance: float | None
    context_coverage: float | None
    failure_type: str | None
    judge_input_tokens: int | None
    judge_output_tokens: int | None
    metadata_json: dict[str, Any]


def _compute_judge_parse_ok(warnings: list[str]) -> bool:
    critical = {
        "empty_judge_response",
        "json_decode_failed",
        "json_root_not_object",
        "balanced_brace_json_invalid",
        "fenced_json_invalid",
    }
    for w in warnings:
        if w in critical:
            return False
        if w.startswith("pydantic_validate_error"):
            return False
    return True


def _sum_tokens(a: int | None, b: int | None) -> int | None:
    if a is None and b is None:
        return None
    return (a or 0) + (b or 0)


def _build_result_from_raw(
    raw: str,
    *,
    model_id: str,
    judge_input_tokens: int | None,
    judge_output_tokens: int | None,
) -> LLMJudgeEvalResult:
    """Single parse pass → result + metadata (no retry keys)."""
    data, w_extract = extract_judge_json_object(raw)
    pr = parse_judge_payload(data, existing_warnings=w_extract)
    all_warnings = pr.warnings

    meta: dict[str, Any] = {
        "evaluator": EVALUATOR_ID,
        "evaluator_type": "llm",
        "judge_prompt_version": JUDGE_PROMPT_VERSION,
        "judge_model": model_id,
        "raw_judge_text_preview": raw[:2000],
        "judge_parse_ok": _compute_judge_parse_ok(all_warnings),
        "judge_parse_warnings": all_warnings,
    }
    meta.update(pr.observability_metadata())

    if judge_input_tokens is not None:
        meta["judge_input_tokens"] = judge_input_tokens
    if judge_output_tokens is not None:
        meta["judge_output_tokens"] = judge_output_tokens

    return LLMJudgeEvalResult(
        faithfulness=pr.scores.get("faithfulness"),
        completeness=pr.scores.get("completeness"),
        groundedness=pr.scores.get("groundedness"),
        retrieval_relevance=pr.scores.get("retrieval_relevance"),
        context_coverage=pr.scores.get("context_coverage"),
        failure_type=pr.failure_type,
        judge_input_tokens=judge_input_tokens,
        judge_output_tokens=judge_output_tokens,
        metadata_json=meta,
    )


def _with_retry_metadata(
    base: LLMJudgeEvalResult,
    *,
    judge_initial_parse_ok: bool,
    judge_retry_attempted: bool,
    judge_retry_succeeded: bool,
    judge_input_tokens: int | None,
    judge_output_tokens: int | None,
) -> LLMJudgeEvalResult:
    m = dict(base.metadata_json)
    m["judge_initial_parse_ok"] = judge_initial_parse_ok
    m["judge_retry_attempted"] = judge_retry_attempted
    m["judge_retry_succeeded"] = judge_retry_succeeded
    if judge_input_tokens is not None:
        m["judge_input_tokens"] = judge_input_tokens
    if judge_output_tokens is not None:
        m["judge_output_tokens"] = judge_output_tokens
    return LLMJudgeEvalResult(
        faithfulness=base.faithfulness,
        completeness=base.completeness,
        groundedness=base.groundedness,
        retrieval_relevance=base.retrieval_relevance,
        context_coverage=base.context_coverage,
        failure_type=base.failure_type,
        judge_input_tokens=judge_input_tokens,
        judge_output_tokens=judge_output_tokens,
        metadata_json=m,
    )


async def evaluate_with_llm_judge(
    *,
    query: str,
    context_chunks: list[str],
    generated_answer: str,
    reference_answer: str | None = None,
    model: str | None = None,
) -> LLMJudgeEvalResult:
    """Call Claude judge; on structural parse failure (**judge_parse_ok** false), retry the API once.

    Transport errors are **not** caught here (propagate to RQ / caller). Only **successful** HTTP responses
    are parsed; a bad structure triggers at most **one** extra judge call.
    """
    client = get_async_anthropic()
    model_id = model or settings.evaluation_model_name
    user_msg = _build_judge_user_payload(
        query=query,
        context_chunks=context_chunks,
        generated_answer=generated_answer,
        reference_answer=reference_answer,
    )

    async def _call_model() -> tuple[str, int | None, int | None]:
        msg = await client.messages.create(
            model=model_id,
            max_tokens=1024,
            system=JUDGE_SYSTEM,
            messages=[{"role": "user", "content": user_msg}],
        )
        text_parts: list[str] = []
        for block in msg.content:
            if hasattr(block, "text"):
                text_parts.append(block.text)
        raw = "\n".join(text_parts).strip()
        inp = getattr(msg.usage, "input_tokens", None)
        out = getattr(msg.usage, "output_tokens", None)
        return raw, inp, out

    raw1, inp1, out1 = await _call_model()
    r1 = _build_result_from_raw(raw1, model_id=model_id, judge_input_tokens=inp1, judge_output_tokens=out1)
    ok1 = bool(r1.metadata_json.get("judge_parse_ok"))

    if ok1:
        return _with_retry_metadata(
            r1,
            judge_initial_parse_ok=True,
            judge_retry_attempted=False,
            judge_retry_succeeded=False,
            judge_input_tokens=inp1,
            judge_output_tokens=out1,
        )

    raw2, inp2, out2 = await _call_model()
    r2 = _build_result_from_raw(raw2, model_id=model_id, judge_input_tokens=inp2, judge_output_tokens=out2)
    ok2 = bool(r2.metadata_json.get("judge_parse_ok"))

    in_tot = _sum_tokens(inp1, inp2)
    out_tot = _sum_tokens(out1, out2)

    # Second response is authoritative (valid parse or safe degradation after retry).
    return _with_retry_metadata(
        r2,
        judge_initial_parse_ok=False,
        judge_retry_attempted=True,
        judge_retry_succeeded=ok2,
        judge_input_tokens=in_tot,
        judge_output_tokens=out_tot,
    )
