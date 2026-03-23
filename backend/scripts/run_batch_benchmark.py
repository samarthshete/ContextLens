#!/usr/bin/env python3
"""Run large-scale benchmark grids via ``app.services.batch_runner.run_batch_benchmark``.

Same query-case ordering is used for every pipeline config (optional ``--seed`` shuffle per dataset).

Examples (from ``backend/``)::

    python scripts/run_batch_benchmark.py \\
        --dataset 1 --dataset 2 \\
        --config 10 --config 11 \\
        --queries-per-dataset 5 \\
        --runs-per-query 3 \\
        --evaluator heuristic

    python scripts/run_batch_benchmark.py -d 1 -c 2 -q 2 -r 2 -e heuristic --realism --seed 42

**LLM** mode runs the full RAG pipeline in-process (requires provider keys + network); use sparingly.

Requires ``alembic upgrade head`` (``runs.metadata_json``).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.database import async_session_maker  # noqa: E402
from app.services.batch_runner import run_batch_benchmark  # noqa: E402
from app.services.benchmark_realism import BenchmarkRealismProfile  # noqa: E402


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Batch benchmark driver (datasets × queries × configs × reps).")
    p.add_argument(
        "-d",
        "--dataset",
        dest="datasets",
        action="append",
        type=int,
        required=True,
        help="Dataset id (repeat for multiple)",
    )
    p.add_argument(
        "-c",
        "--config",
        dest="configs",
        action="append",
        type=int,
        required=True,
        help="Pipeline config id (repeat for multiple)",
    )
    p.add_argument(
        "-q",
        "--queries-per-dataset",
        type=int,
        default=10,
        help="Max query cases per dataset (stable id order; shuffle with --seed)",
    )
    p.add_argument(
        "-r",
        "--runs-per-query",
        type=int,
        default=1,
        help="Repetitions per (query × config) cell",
    )
    p.add_argument(
        "-e",
        "--evaluator",
        choices=("heuristic", "llm"),
        default="heuristic",
        help="heuristic = inline retrieval+eval; llm = full RAG in-process",
    )
    p.add_argument("--seed", type=int, default=None, help="Random seed for query shuffle (per dataset)")
    p.add_argument("--experiment-name", default=None)
    p.add_argument("--config-group-tag", default=None)
    p.add_argument("--document-id", type=int, default=None, help="Optional retrieval document scope")
    p.add_argument(
        "--realism",
        action="store_true",
        help="Enable heuristic retrieval/score perturbations (batch_runner BenchmarkRealismProfile defaults)",
    )
    p.add_argument(
        "--strict",
        action="store_true",
        help="Exit with code 1 if any cell failed",
    )
    return p.parse_args()


async def _async_main(ns: argparse.Namespace) -> int:
    realism = BenchmarkRealismProfile() if ns.realism else None
    async with async_session_maker() as session:
        result = await run_batch_benchmark(
            session,
            ns.datasets,
            ns.configs,
            ns.queries_per_dataset,
            ns.runs_per_query,
            ns.evaluator,
            random_seed=ns.seed,
            document_id=ns.document_id,
            experiment_name=ns.experiment_name,
            config_group_tag=ns.config_group_tag,
            realism_profile=realism,
            commit=True,
        )
    print(
        json.dumps(
            {
                "batch_id": result.batch_id,
                "total_runs": result.total_runs,
                "successes": result.successes,
                "failures": result.failures,
                "success_rate": round(result.success_rate, 6),
            },
            indent=2,
        )
    )
    if ns.strict and result.failures > 0:
        return 1
    return 0


def main() -> None:
    ns = _parse_args()
    raise SystemExit(asyncio.run(_async_main(ns)))


if __name__ == "__main__":
    main()
