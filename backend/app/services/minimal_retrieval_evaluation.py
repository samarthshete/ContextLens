"""Deterministic evaluation from persisted retrieval rows + chunk text.

No LLM calls: scores are derived from stored cosine-similarity ranks and simple
lexical overlap. Use ``metadata_json`` on the evaluation row to record the
evaluator id for downstream reporting.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.failure_taxonomy import FailureType
from app.models import Chunk, QueryCase, RetrievalResult, Run

_WORD = re.compile(r"[a-z0-9]+", re.I)

EVALUATOR_ID = "minimal_retrieval_heuristic_v1"

# Heuristic failure thresholds (fixed; batch realism may re-classify after score noise).
RELEVANCE_PARTIAL_THRESHOLD = 0.3
CONTEXT_INSUFFICIENT_THRESHOLD = 0.4
COMPLETENESS_INCOMPLETE_THRESHOLD = 0.5


def classify_heuristic_failure_from_scores(
    *,
    retrieval_miss: bool,
    retrieval_relevance: float | None,
    context_coverage: float | None,
    completeness: float | None,
) -> str:
    """Map scores to taxonomy. **NO_FAILURE** only when all applicable checks pass.

    Order: retrieval miss → low relevance → low coverage → low completeness → OK.
    """
    if retrieval_miss:
        return FailureType.RETRIEVAL_MISS.value
    if retrieval_relevance is not None and retrieval_relevance < RELEVANCE_PARTIAL_THRESHOLD:
        return FailureType.RETRIEVAL_PARTIAL.value
    if context_coverage is not None and context_coverage < CONTEXT_INSUFFICIENT_THRESHOLD:
        return FailureType.CONTEXT_INSUFFICIENT.value
    if completeness is not None and completeness < COMPLETENESS_INCOMPLETE_THRESHOLD:
        return FailureType.ANSWER_INCOMPLETE.value
    return FailureType.NO_FAILURE.value


def significant_tokens(text: str) -> set[str]:
    """Lowercase alphanumeric tokens of length >= 2."""
    return {m.group(0).lower() for m in _WORD.finditer(text or "") if len(m.group(0)) >= 2}


def token_recall(query_tokens: set[str], corpus_text: str) -> float | None:
    """Fraction of *query_tokens* that appear in *corpus_text* (0..1)."""
    if not query_tokens:
        return None
    against = significant_tokens(corpus_text)
    if not against:
        return 0.0
    hits = len(query_tokens & against)
    return hits / len(query_tokens)


@dataclass(frozen=True, slots=True)
class MinimalRetrievalEvalScores:
    """Numeric outputs suitable for ``evaluation_results`` (no timings)."""

    faithfulness: float | None
    completeness: float | None
    retrieval_relevance: float | None
    context_coverage: float | None
    failure_type: str | None
    used_llm_judge: bool
    metadata_json: dict[str, Any]


async def compute_minimal_retrieval_evaluation(
    session: AsyncSession,
    *,
    run_id: int,
) -> MinimalRetrievalEvalScores:
    """Load retrieval rows for *run_id* and compute heuristic scores.

    - **retrieval_relevance**: mean of persisted retrieval ``score`` values.
    - **context_coverage**: token recall of the query text in concatenated
      retrieved chunk bodies.
    - **completeness**: if ``QueryCase.expected_answer`` is set, token recall of
      that answer in concatenated chunk bodies; else ``None``.
    - **faithfulness**: ``None`` (no stored generated answer to verify).
    """
    run = await session.get(Run, run_id)
    if run is None:
        raise ValueError(f"Run id={run_id} not found")

    qc = await session.get(QueryCase, run.query_case_id)
    if qc is None:
        raise ValueError(f"QueryCase for run id={run_id} not found")

    stmt = (
        select(RetrievalResult, Chunk.content)
        .join(Chunk, Chunk.id == RetrievalResult.chunk_id)
        .where(RetrievalResult.run_id == run_id)
        .order_by(RetrievalResult.rank)
    )
    rows = (await session.execute(stmt)).all()
    if not rows:
        return MinimalRetrievalEvalScores(
            faithfulness=None,
            completeness=None,
            retrieval_relevance=None,
            context_coverage=None,
            failure_type=FailureType.RETRIEVAL_MISS.value,
            used_llm_judge=False,
            metadata_json={
                "evaluator": EVALUATOR_ID,
                "evaluator_type": "heuristic",
                "note": "No retrieval_results for this run.",
            },
        )

    scores = [float(rr.score) for rr, _ in rows]
    retrieval_relevance = sum(scores) / len(scores)

    chunk_text = "\n\n".join(content for _, content in rows)
    q_tokens = significant_tokens(qc.query_text)
    context_coverage = token_recall(q_tokens, chunk_text)

    completeness: float | None = None
    if qc.expected_answer and qc.expected_answer.strip():
        completeness = token_recall(significant_tokens(qc.expected_answer), chunk_text)

    meta: dict[str, Any] = {
        "evaluator": EVALUATOR_ID,
        "evaluator_type": "heuristic",
        "description": (
            "Heuristic metrics from stored retrieval scores and lexical overlap; "
            "no LLM judge and no faithfulness (no generated answer persisted)."
        ),
        "failure_rules": {
            "relevance_lt": RELEVANCE_PARTIAL_THRESHOLD,
            "context_coverage_lt": CONTEXT_INSUFFICIENT_THRESHOLD,
            "completeness_lt": COMPLETENESS_INCOMPLETE_THRESHOLD,
        },
    }

    failure_type = classify_heuristic_failure_from_scores(
        retrieval_miss=False,
        retrieval_relevance=retrieval_relevance,
        context_coverage=context_coverage,
        completeness=completeness,
    )

    return MinimalRetrievalEvalScores(
        faithfulness=None,
        completeness=completeness,
        retrieval_relevance=retrieval_relevance,
        context_coverage=context_coverage,
        failure_type=failure_type,
        used_llm_judge=False,
        metadata_json=meta,
    )


HYBRID_GATE_MAX_CHUNK_SCORE = 0.88
HYBRID_GATE_MEAN_RELEVANCE = 0.55
HYBRID_GATE_CONTEXT_COVERAGE = 0.42


def hybrid_retrieval_gate_passes(
    *,
    max_chunk_score: float,
    retrieval_relevance: float | None,
    context_coverage: float | None,
) -> bool:
    """When True, hybrid full-RAG may skip the LLM judge (persisted heuristic-style eval instead)."""
    if retrieval_relevance is None or context_coverage is None:
        return False
    return (
        max_chunk_score >= HYBRID_GATE_MAX_CHUNK_SCORE
        and retrieval_relevance >= HYBRID_GATE_MEAN_RELEVANCE
        and context_coverage >= HYBRID_GATE_CONTEXT_COVERAGE
    )


async def compute_hybrid_skipped_evaluation(
    session: AsyncSession,
    *,
    run_id: int,
    generated_answer: str,
) -> MinimalRetrievalEvalScores:
    """Heuristic final scores after generation when the hybrid gate skips the LLM judge.

    **Faithfulness** is lexical recall of generated-answer tokens against retrieved context
    (not entailment). Documented in evaluation ``metadata_json`` for honest downstream use.
    """
    base = await compute_minimal_retrieval_evaluation(session, run_id=run_id)
    run = await session.get(Run, run_id)
    if run is None:
        raise ValueError(f"Run id={run_id} not found")
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
    if not rows:
        return base

    chunk_text = "\n\n".join(content for _, content in rows)
    gen_tokens = significant_tokens(generated_answer)
    faithfulness = token_recall(gen_tokens, chunk_text)

    failure_type = classify_heuristic_failure_from_scores(
        retrieval_miss=False,
        retrieval_relevance=base.retrieval_relevance,
        context_coverage=base.context_coverage,
        completeness=base.completeness,
    )

    meta = dict(base.metadata_json or {})
    meta.update(
        {
            "evaluator": f"{EVALUATOR_ID}_hybrid_gate_skip",
            "evaluator_type": "heuristic",
            "hybrid_judge_skipped": True,
            "description": (
                "Hybrid gate skipped LLM judge: scores from retrieval heuristics plus "
                "lexical faithfulness (generated answer token recall in retrieved context)."
            ),
        }
    )

    return MinimalRetrievalEvalScores(
        faithfulness=faithfulness,
        completeness=base.completeness,
        retrieval_relevance=base.retrieval_relevance,
        context_coverage=base.context_coverage,
        failure_type=failure_type,
        used_llm_judge=False,
        metadata_json=meta,
    )
