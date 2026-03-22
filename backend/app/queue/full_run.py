"""Enqueue full benchmark pipeline jobs (RQ)."""

from __future__ import annotations

import logging
from datetime import datetime

from redis.exceptions import RedisError
from rq import Queue, Retry
from rq.job import Job
from rq.registry import (
    DeferredJobRegistry,
    FailedJobRegistry,
    FinishedJobRegistry,
    ScheduledJobRegistry,
    StartedJobRegistry,
)

from app.queue.connection import get_sync_redis
from app.workers.full_run_worker import full_benchmark_run_job, full_run_on_failure

logger = logging.getLogger(__name__)

QUEUE_NAME = "contextlens_full_run"


def get_full_run_queue() -> Queue:
    return Queue(QUEUE_NAME, connection=get_sync_redis())


def enqueue_full_benchmark_run(run_id: int, document_id: int | None) -> str:
    """Push a full-run job. Returns RQ job id.

    Retries up to **3 attempts** total (1 run + 2 retries) on failure, with backoff.
    After retries are exhausted, ``full_run_on_failure`` marks the run ``failed``.

    Raises:
        redis.exceptions.RedisError: If Redis is unreachable (caller maps to HTTP 503).
    """
    queue = get_full_run_queue()
    # max=2 → RQ runs the job once plus two retries (three attempts).
    retry = Retry(max=2, interval=[15, 45])
    job = queue.enqueue(
        full_benchmark_run_job,
        run_id,
        document_id,
        job_timeout=3600,
        retry=retry,
        on_failure=full_run_on_failure,
        failure_ttl=86400,
    )
    jid = job.id
    logger.info("enqueued full benchmark job_id=%s run_id=%s", jid, run_id)
    return jid


def ping_redis() -> bool:
    """Return True if Redis responds to PING."""
    try:
        return bool(get_sync_redis().ping())
    except RedisError:
        return False


def _rq_job_sort_ts(job: Job) -> float:
    """Best-effort monotonic timestamp for picking the newest job for a run_id."""
    for attr in ("enqueued_at", "created_at", "started_at", "ended_at"):
        v = getattr(job, attr, None)
        if v is None:
            continue
        if isinstance(v, datetime):
            return v.timestamp()
        if isinstance(v, (int, float)):
            return float(v)
    return 0.0


def _iter_full_run_queue_job_ids(queue: Queue, connection) -> set[str]:
    ids: set[str] = set(queue.get_job_ids())
    for reg_cls in (
        StartedJobRegistry,
        FinishedJobRegistry,
        FailedJobRegistry,
        DeferredJobRegistry,
        ScheduledJobRegistry,
    ):
        reg = reg_cls(queue.name, connection=connection)
        ids.update(reg.get_job_ids())
    return ids


def find_primary_job_for_run(run_id: int) -> tuple[str | None, str | None]:
    """Best-effort: newest RQ job in the full-run queue whose first arg is ``run_id``.

    Returns ``(job_id, rq_status)`` or ``(None, None)`` if none found or fetch fails.
    Job ids are **not** stored on ``runs`` rows; this scans queue registries only.

    Raises:
        RedisError: connection / server errors (caller may map to HTTP 503).
    """
    connection = get_sync_redis()
    queue = get_full_run_queue()
    candidates: list[tuple[float, str, Job]] = []
    for jid in _iter_full_run_queue_job_ids(queue, connection):
        try:
            job = Job.fetch(jid, connection=connection)
        except Exception:
            logger.debug("find_primary_job_for_run: skip bad job id=%s", jid, exc_info=True)
            continue
        args = job.args or ()
        try:
            if not args or int(args[0]) != int(run_id):
                continue
        except (TypeError, ValueError):
            continue
        ts = _rq_job_sort_ts(job)
        candidates.append((ts, jid, job))

    if not candidates:
        return None, None

    candidates.sort(key=lambda t: t[0], reverse=True)
    _, best_id, best_job = candidates[0]
    status = best_job.get_status()
    if hasattr(status, "value"):
        status_str = str(status.value)
    else:
        status_str = str(status).lower()
    return best_id, status_str
