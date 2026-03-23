#!/usr/bin/env python3
"""Seed registry + ingest narrow corpus for evidence-stress-v1.

Usage (from ``backend/``)::

    python scripts/seed_evidence_stress_benchmark.py
    python scripts/seed_evidence_stress_benchmark.py --stress-dir /path/to/evidence-stress-v1
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
from app.services.benchmark_stress_seed import (  # noqa: E402
    ensure_stress_benchmark_seed,
    ensure_stress_corpus_document,
)


async def _main(stress_dir: Path | None) -> None:
    async with async_session_maker() as session:
        r = await ensure_stress_benchmark_seed(session, stress_dir, commit=True)
        doc = await ensure_stress_corpus_document(session, stress_dir, commit=True)
    print("Evidence stress benchmark seed OK (idempotent).")
    print(f"  dataset_id={r.dataset_id}")
    print(f"  query_case_ids={r.query_case_ids}")
    print(f"  pipeline_config_ids={r.pipeline_config_ids}")
    print(f"  document_id={doc.id}")


def main() -> None:
    p = argparse.ArgumentParser(description="Seed evidence-stress-v1 registry + corpus.")
    p.add_argument(
        "--stress-dir",
        type=Path,
        default=None,
        help="Path to benchmark-datasets/evidence-stress-v1",
    )
    args = p.parse_args()
    sd = args.stress_dir.resolve() if args.stress_dir else None
    asyncio.run(_main(sd))


if __name__ == "__main__":
    main()
