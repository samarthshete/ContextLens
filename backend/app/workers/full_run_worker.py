"""RQ worker job: durable full benchmark (retrieval → generation → LLM judge)."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from redis.exceptions import RedisError

from app.queue.connection import get_sync_redis
from app.services.run_create import mark_run_failed_sync, run_full_benchmark_pipeline

logger = logging.getLogger(__name__)

FULL_RUN_LOCK_KEY = "contextlens:full_run_lock:{run_id}"
LOCK_TTL_SEC = 3600


def full_benchmark_run_job(run_id: int, document_id: int | None = None) -> None:
    """Sync entry point for RQ. Uses a Redis lock to avoid duplicate concurrent work on ``run_id``."""
    redis = get_sync_redis()
    key = FULL_RUN_LOCK_KEY.format(run_id=run_id)
    try:
        got = redis.set(key, b"1", nx=True, ex=LOCK_TTL_SEC)
    except RedisError:
        logger.exception("full_run job: Redis lock error run_id=%s", run_id)
        raise
    if not got:
        logger.info(
            "full_run job: lock not acquired run_id=%s (another worker holds it); exiting",
            run_id,
        )
        return
    try:
        asyncio.run(run_full_benchmark_pipeline(run_id, document_id))
    finally:
        try:
            redis.delete(key)
        except RedisError:
            logger.warning("full_run job: could not release lock run_id=%s", run_id)


def full_run_on_failure(job: Any, *args: Any, **kwargs: Any) -> None:
    """RQ callback after all retries are exhausted (RQ passes ``job`` plus connection / exc info)."""
    exc_value = next((a for a in args if isinstance(a, BaseException)), None)
    try:
        ja = job.args or ()
        run_id = int(ja[0]) if ja else None
    except (TypeError, ValueError, IndexError):
        logger.exception("full_run_on_failure: bad job args")
        return
    if run_id is None:
        return
    logger.error(
        "full_run_on_failure: marking run failed run_id=%s after retries: %s",
        run_id,
        exc_value,
    )
    mark_run_failed_sync(run_id)
