#!/usr/bin/env python3
"""Pre-flight: verify Redis is reachable for RQ full-run jobs.

Usage (from repo):
    cd backend && python scripts/check_redis_for_rq.py

Uses ``REDIS_URL`` from app settings (default ``redis://localhost:6379/0``).
Exit 0 if PING succeeds, 1 otherwise.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow `python scripts/check_redis_for_rq.py` without installing the package as CWD on PYTHONPATH
_backend_root = Path(__file__).resolve().parent.parent
if str(_backend_root) not in sys.path:
    sys.path.insert(0, str(_backend_root))

from app.queue.full_run import ping_redis  # noqa: E402


def main() -> int:
    if ping_redis():
        print("OK: Redis responds — full runs can enqueue (RQ).")
        return 0
    print(
        "FAIL: Redis unreachable. Start Redis and set REDIS_URL "
        "(e.g. redis://localhost:6379/0). See docs/DEV_FULL_RUN_QUEUE.md",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
