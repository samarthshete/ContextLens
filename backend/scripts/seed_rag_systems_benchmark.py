#!/usr/bin/env python3
"""Idempotent registry + three ingested corpus variants for rag_systems_retrieval_engineering_v1.

Does not run benchmark pairs — use ``run_rag_systems_benchmark.py``.

Usage (from ``backend/``)::

    python scripts/seed_rag_systems_benchmark.py
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
from app.services.benchmark_rag_systems_seed import (  # noqa: E402
    ensure_rag_systems_benchmark_seed,
)


async def _main(data_dir: Path | None) -> None:
    async with async_session_maker() as session:
        r = await ensure_rag_systems_benchmark_seed(session, data_dir, commit=True)
    print("RAG systems benchmark seed OK (idempotent).")
    print(f"  dataset_id={r.dataset_id}")
    print(f"  query_case_ids={r.query_case_ids}")
    for name, pc_id, doc_id in r.run_plan:
        print(f"  {name}: pipeline_config_id={pc_id} scoped_document_id={doc_id}")


def main() -> None:
    p = argparse.ArgumentParser(description="Seed rag_systems_retrieval_engineering_v1.")
    p.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        help="Path to benchmark_data/rag_systems_retrieval_engineering_v1 (default: under backend/).",
    )
    args = p.parse_args()
    data_dir = args.data_dir.resolve() if args.data_dir else None
    asyncio.run(_main(data_dir))


if __name__ == "__main__":
    main()
