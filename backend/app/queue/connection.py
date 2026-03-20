"""Sync Redis connection for RQ (workers and API enqueue)."""

from __future__ import annotations

from functools import lru_cache

from redis import Redis

from app.config import settings


@lru_cache
def get_sync_redis() -> Redis:
    """Shared sync Redis client (decode_responses=False for RQ compatibility)."""
    return Redis.from_url(settings.redis_url, decode_responses=False)
