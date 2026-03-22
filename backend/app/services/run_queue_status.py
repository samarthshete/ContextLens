"""Read-only queue / lock inspection for full benchmark runs."""

from __future__ import annotations

import logging
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import EvaluationResult, GenerationResult, Run
from app.queue.full_run import find_primary_job_for_run
from app.queue.connection import get_sync_redis
from app.schemas.run_queue_status import RunQueueStatusResponse
from app.services.run_requeue import (
    RunNotFoundError,
    evaluate_structural_requeue_eligibility,
    infer_pipeline_heuristic_vs_full,
)
from app.workers.full_run_worker import (
    FULL_RUN_LOCK_KEY,
    clear_stale_full_run_lock_if_applicable,
)

logger = logging.getLogger(__name__)


async def _load_gen_ev(
    session: AsyncSession,
    run_id: int,
) -> tuple[GenerationResult | None, EvaluationResult | None]:
    gen = (
        await session.execute(select(GenerationResult).where(GenerationResult.run_id == run_id))
    ).scalar_one_or_none()
    ev = (
        await session.execute(select(EvaluationResult).where(EvaluationResult.run_id == run_id))
    ).scalar_one_or_none()
    return gen, ev


async def get_run_queue_status(
    session: AsyncSession,
    run_id: int,
) -> RunQueueStatusResponse:
    """Inspect RQ + Redis lock for a run. **404** → raise ``RunNotFoundError``.

    Heuristic runs skip Redis/RQ calls. Full runs require Redis for lock/job fields;
    raises ``RedisError`` if Redis is unreachable (map to HTTP 503 at the route).

    Does **not** guarantee that an RQ job still exists after completion (TTL / registry
    eviction). ``job_id`` is best-effort from scanning the full-run queue only.
    """
    run = await session.get(Run, run_id)
    if run is None:
        raise RunNotFoundError(run_id)

    gen, ev = await _load_gen_ev(session, run_id)
    pipeline = infer_pipeline_heuristic_vs_full(generation=gen, evaluation=ev)
    struct_ok, struct_msg = evaluate_structural_requeue_eligibility(run, gen, ev)

    if pipeline == "heuristic":
        return RunQueueStatusResponse(
            run_id=run.id,
            run_status=run.status,
            pipeline="heuristic",
            job_id=None,
            rq_job_status=None,
            lock_present=False,
            requeue_eligible=False,
            detail=struct_msg,
        )

    lock_key = FULL_RUN_LOCK_KEY.format(run_id=run_id)

    job_id: str | None = None
    rq_job_status: str | None = None
    try:
        job_id, rq_job_status = find_primary_job_for_run(run_id)
    except RedisError:
        logger.exception("queue-status: Redis error scanning jobs run_id=%s", run_id)
        raise
    except Exception:
        logger.exception("queue-status: unexpected error scanning RQ run_id=%s", run_id)
        job_id, rq_job_status = None, None

    try:
        clear_stale_full_run_lock_if_applicable(
            run_id=run_id,
            run_status=run.status,
            job_id=job_id,
            rq_job_status=rq_job_status,
        )
        lock_present = int(get_sync_redis().exists(lock_key)) > 0
    except RedisError:
        logger.exception("queue-status: Redis error checking lock run_id=%s", run_id)
        raise

    requeue_eligible = struct_ok and not lock_present
    detail: str | None = None
    if not struct_ok:
        detail = struct_msg
    elif lock_present:
        detail = (
            "A full-run worker lock is held for this run_id; wait for it to finish or expire."
        )

    return RunQueueStatusResponse(
        run_id=run.id,
        run_status=run.status,
        pipeline="full",
        job_id=job_id,
        rq_job_status=rq_job_status,
        lock_present=lock_present,
        requeue_eligible=requeue_eligible,
        detail=detail,
    )
