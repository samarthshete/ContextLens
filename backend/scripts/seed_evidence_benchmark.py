#!/usr/bin/env python3
"""Idempotent evidence benchmark registry (dataset, queries, pipeline configs).

Does not ingest the combined corpus or run retrieval — use ``run_evidence_benchmark.py``.

Usage (from ``backend/``)::

    python scripts/seed_evidence_benchmark.py
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.database import async_session_maker  # noqa: E402
from app.services.benchmark_evidence_seed import ensure_evidence_benchmark_seed  # noqa: E402


async def _main(evidence_dir: Path | None) -> None:
    async with async_session_maker() as session:
        r = await ensure_evidence_benchmark_seed(session, evidence_dir, commit=True)
    print("Evidence benchmark seed OK (idempotent).")
    print(f"  dataset_id={r.dataset_id}")
    print(f"  query_case_ids={r.query_case_ids}")
    print(f"  pipeline_config_ids={r.pipeline_config_ids}")


def main() -> None:
    p = argparse.ArgumentParser(description="Seed evidence-rag-v1 registry rows.")
    p.add_argument(
        "--evidence-dir",
        type=Path,
        default=None,
        help="Path to benchmark-datasets/evidence-rag-v1 (default: repo default).",
    )
    args = p.parse_args()
    evidence_dir = args.evidence_dir.resolve() if args.evidence_dir else None
    asyncio.run(_main(evidence_dir))


if __name__ == "__main__":
    main()
