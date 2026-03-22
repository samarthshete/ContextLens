#!/usr/bin/env sh
# RQ worker for full benchmark runs — used by Docker Compose and Render worker service.
# Requires REDIS_URL (same value API uses for enqueue).
set -eu
exec rq worker contextlens_full_run --url "${REDIS_URL:?REDIS_URL is required}"
