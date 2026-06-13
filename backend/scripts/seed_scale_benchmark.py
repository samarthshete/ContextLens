#!/usr/bin/env python3
"""Seed the 52-query scale benchmark (dataset, queries, configs, one corpus document)."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.database import async_session_maker  # noqa: E402
from app.services.benchmark_scale_seed import ensure_scale_benchmark_ready  # noqa: E402


async def _main() -> None:
    async with async_session_maker() as session:
        r = await ensure_scale_benchmark_ready(session)
    print(
        json.dumps(
            {
                "dataset_id": r.dataset_id,
                "document_id": r.document_id,
                "query_case_count": len(r.query_case_ids),
                "pipeline_config_ids": list(r.pipeline_config_ids),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(_main())
