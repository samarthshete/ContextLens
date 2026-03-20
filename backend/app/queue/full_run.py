"""Enqueue full benchmark pipeline jobs (RQ)."""

from __future__ import annotations

import logging

from redis.exceptions import RedisError
from rq import Queue, Retry

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
