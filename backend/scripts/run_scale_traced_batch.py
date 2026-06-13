#!/usr/bin/env python3
"""Print IDs after seeding + example batch commands for 150+ traced heuristic runs (52 queries × 2 configs × 2 reps).

Run from ``backend/`` after ``alembic upgrade head``::

    python scripts/seed_scale_benchmark.py
    python scripts/run_scale_traced_batch.py

Then execute the printed ``run_batch_benchmark.py`` line(s) with your dataset/config IDs.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.database import async_session_maker  # noqa: E402
from app.services.benchmark_scale_seed import ensure_scale_benchmark_ready  # noqa: E402


async def _main() -> None:
    async with async_session_maker() as session:
        r = await ensure_scale_benchmark_ready(session)
    d, c1, c2 = r.dataset_id, r.pipeline_config_ids[0], r.pipeline_config_ids[1]
    doc = r.document_id
    print(json.dumps({"dataset_id": d, "config_ids": [c1, c2], "document_id": doc}, indent=2))
    print()
    print("Example — 208 traced heuristic runs (52 × 2 configs × 2 reps), scoped to corpus doc:")
    print(
        f"  python scripts/run_batch_benchmark.py -d {d} -c {c1} -c {c2} "
        f"-q 52 -r 2 -e heuristic --document-id {doc}"
    )
    print()
    print("Example — 156 runs (52 × 3 reps × 1 config):")
    print(f"  python scripts/run_batch_benchmark.py -d {d} -c {c1} -q 52 -r 3 -e heuristic --document-id {doc}")
    print()
    print("Matched LLM vs hybrid comparison (requires API keys; same workload UUID for both):")
    print(
        f"  WORKLOAD=$(python -c 'import uuid; print(uuid.uuid4())') && "
        f"python scripts/run_batch_benchmark.py -d {d} -c {c1} -q 5 -r 1 -e llm "
        f"--document-id {doc} --matched-llm-reduction-workload-id $WORKLOAD && "
        f"python scripts/run_batch_benchmark.py -d {d} -c {c1} -q 5 -r 1 -e llm_hybrid "
        f"--document-id {doc} --matched-llm-reduction-workload-id $WORKLOAD"
    )


if __name__ == "__main__":
    asyncio.run(_main())
