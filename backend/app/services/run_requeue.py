"""Re-enqueue a durable full benchmark run (same RQ path as POST /runs eval_mode=full)."""

from __future__ import annotations

import logging
from typing import Final, Literal

from redis.exceptions import RedisError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.evaluator_bucket import resolved_evaluator_type
from app.models import Chunk, EvaluationResult, GenerationResult, RetrievalResult, Run
from app.queue.connection import get_sync_redis
from app.queue.full_run import enqueue_full_benchmark_run, find_primary_job_for_run
from app.services.llm_provider_keys import require_llm_api_key_for_full_mode
from app.services.run_lifecycle import (
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_GENERATION_COMPLETED,
    STATUS_RETRIEVAL_COMPLETED,
    STATUS_RUNNING,
)
from app.workers.full_run_worker import (
    FULL_RUN_LOCK_KEY,
    clear_stale_full_run_lock_if_applicable,
)

logger = logging.getLogger(__name__)

ALLOW_REQUEUE_STATUSES: Final[frozenset[str]] = frozenset(
    {
        STATUS_RUNNING,
        STATUS_RETRIEVAL_COMPLETED,
        STATUS_GENERATION_COMPLETED,
        STATUS_FAILED,
    }
)


class RunNotFoundError(LookupError):
    """No ``runs`` row for the given id."""


class RunRequeueConflictError(Exception):
    """Run is not eligible for full-run re-enqueue."""

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


def infer_pipeline_heuristic_vs_full(
    *,
    generation: GenerationResult | None,
    evaluation: EvaluationResult | None,
) -> Literal["heuristic", "full"]:
    """``heuristic`` when the persisted trace matches the heuristic-only requeue exclusion."""
    if _is_heuristic_only_evaluated_run(generation=generation, evaluation=evaluation):
        return "heuristic"
    return "full"


def _is_heuristic_only_evaluated_run(
    *,
    generation: GenerationResult | None,
    evaluation: EvaluationResult | None,
) -> bool:
    """True if an evaluation row clearly belongs to the heuristic bucket (never full RAG)."""
    if generation is not None:
        return False
    if evaluation is None:
        return False
    return (
        resolved_evaluator_type(
            used_llm_judge=evaluation.used_llm_judge,
            metadata_json=evaluation.metadata_json,
        )
        == "heuristic"
    )


async def _normalize_failed_run_for_resume(session: AsyncSession, run: Run) -> None:
    """If ``run.status == failed``, set a resumable status from persisted phase rows (mutates ``run``).

    The worker skips **failed** and **completed**; after normalization we only enqueue when the row
    reflects a phase the worker can continue from.
    """
    if run.status != STATUS_FAILED:
        return

    gen = (
        await session.execute(select(GenerationResult).where(GenerationResult.run_id == run.id))
    ).scalar_one_or_none()
    if gen is not None:
        run.status = STATUS_GENERATION_COMPLETED
        return

    rc = (
        await session.execute(
            select(func.count()).select_from(RetrievalResult).where(RetrievalResult.run_id == run.id)
        )
    ).scalar_one()
    if int(rc) > 0:
        run.status = STATUS_RETRIEVAL_COMPLETED
        return

    run.status = STATUS_RUNNING


async def infer_document_id_for_full_run(session: AsyncSession, run_id: int) -> int | None:
    """If all retrieval hits for this run point at one document, return it; else ``None``."""
    stmt = (
        select(Chunk.document_id)
        .join(RetrievalResult, RetrievalResult.chunk_id == Chunk.id)
        .where(RetrievalResult.run_id == run_id)
        .distinct()
    )
    rows = list((await session.execute(stmt)).scalars().all())
    if len(rows) == 1:
        return int(rows[0])
    return None


def evaluate_structural_requeue_eligibility(
    run: Run,
    gen_result: GenerationResult | None,
    ev_result: EvaluationResult | None,
) -> tuple[bool, str | None]:
    """Return whether this run could be re-enqueued, ignoring API key, Redis lock, and enqueue."""
    if run.status == STATUS_COMPLETED:
        return False, "Run is already completed."

    if run.status not in ALLOW_REQUEUE_STATUSES:
        return False, (
            f"Run status {run.status!r} is not eligible for re-enqueue "
            f"(allowed: {', '.join(sorted(ALLOW_REQUEUE_STATUSES))})."
        )

    if _is_heuristic_only_evaluated_run(generation=gen_result, evaluation=ev_result):
        return False, (
            "Run is a heuristic benchmark (no full RAG pipeline); re-enqueue is not supported."
        )

    return True, None


async def structural_requeue_eligibility(
    session: AsyncSession,
    run: Run,
) -> tuple[bool, str | None]:
    """Load trace rows then :func:`evaluate_structural_requeue_eligibility`."""
    gen_result = (
        await session.execute(select(GenerationResult).where(GenerationResult.run_id == run.id))
    ).scalar_one_or_none()
    ev_result = (
        await session.execute(select(EvaluationResult).where(EvaluationResult.run_id == run.id))
    ).scalar_one_or_none()
    return evaluate_structural_requeue_eligibility(run, gen_result, ev_result)


async def requeue_full_run(session: AsyncSession, run_id: int) -> tuple[Run, str]:
    """Validate eligibility, then enqueue ``full_benchmark_run_job`` for ``run_id``.

    Does **not** create a new run row or mutate benchmark logic — only pushes a new RQ job
    with the same ``run_id`` and inferred ``document_id`` scope.

    Returns:
        ``(run, job_id)``

    Raises:
        RunNotFoundError: 404
        RunRequeueConflictError: 409 (wrong mode, terminal state, lock held, etc.)
        RedisError: propagate to route → 503
        ValueError: missing API key from ``require_llm_api_key_for_full_mode`` → route maps to 503
    """
    run = await session.get(Run, run_id)
    if run is None:
        raise RunNotFoundError(run_id)

    ok, msg = await structural_requeue_eligibility(session, run)
    if not ok:
        raise RunRequeueConflictError(msg or "Run is not eligible for re-enqueue.")

    try:
        jid, jst = find_primary_job_for_run(run_id)
    except RedisError:
        logger.exception("requeue: Redis error scanning jobs run_id=%s", run_id)
        raise
    except Exception:
        logger.exception("requeue: unexpected error scanning RQ run_id=%s", run_id)
        jid, jst = None, None

    clear_stale_full_run_lock_if_applicable(
        run_id=run_id,
        run_status=run.status,
        job_id=jid,
        rq_job_status=jst,
    )

    require_llm_api_key_for_full_mode()

    lock_key = FULL_RUN_LOCK_KEY.format(run_id=run_id)
    try:
        if int(get_sync_redis().exists(lock_key)) > 0:
            raise RunRequeueConflictError(
                "A full-run worker lock is held for this run_id; wait for it to finish or expire."
            )
    except RedisError:
        logger.exception("requeue: Redis error checking lock run_id=%s", run_id)
        raise

    if run.status == STATUS_FAILED:
        await _normalize_failed_run_for_resume(session, run)
        await session.commit()
        await session.refresh(run)

    document_id = await infer_document_id_for_full_run(session, run_id)
    job_id = enqueue_full_benchmark_run(run_id, document_id)
    logger.info("requeued full benchmark job_id=%s run_id=%s document_id=%s", job_id, run_id, document_id)
    return run, job_id
