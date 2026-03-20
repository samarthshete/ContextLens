#!/usr/bin/env python3
"""Idempotent benchmark registry: dataset, query cases, pipeline configs.

Does not run retrieval, ingest a corpus, or write evaluation rows.

Usage (from ``backend/``)::

    python scripts/seed_benchmark.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.database import async_session_maker  # noqa: E402
from app.services.benchmark_seed import ensure_benchmark_seed  # noqa: E402


async def _main() -> None:
    async with async_session_maker() as session:
        r = await ensure_benchmark_seed(session, commit=True)
    print("Benchmark seed OK (idempotent).")
    print(f"  dataset_id={r.dataset_id}")
    print(f"  query_case_ids={r.query_case_ids}")
    print(f"  pipeline_config_ids={r.pipeline_config_ids}")


def main() -> None:
    asyncio.run(_main())


if __name__ == "__main__":
    main()
