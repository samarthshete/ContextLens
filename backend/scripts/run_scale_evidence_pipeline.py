#!/usr/bin/env python3
"""One-command scale evidence pipeline: seed + execute 208 traced runs + verify dashboard counts.

Usage (from backend/ or via Docker)::

    python scripts/run_scale_evidence_pipeline.py
    python scripts/run_scale_evidence_pipeline.py --reps 3        # 312 runs = 52×2×3
    python scripts/run_scale_evidence_pipeline.py --force-recreate # rebuild dataset if invalid

Requires ``alembic upgrade head`` before first run.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from sqlalchemy import delete, select, func  # noqa: E402

from app.database import async_session_maker  # noqa: E402
from app.models import Dataset, EvaluationResult, QueryCase, Run  # noqa: E402
from app.services.batch_runner import run_batch_benchmark  # noqa: E402
from app.services.benchmark_scale_seed import (  # noqa: E402
    SCALE_DATASET_NAME,
    SCALE_DOC_TITLE,
    ensure_scale_benchmark_ready,
    ScaleBenchmarkSeedResult,
)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Seed + execute 52-query scale benchmark + verify dashboard evidence."
    )
    p.add_argument(
        "--reps",
        type=int,
        default=2,
        help="Repetitions per (query × config) cell. Default 2 → 208 runs.",
    )
    p.add_argument(
        "--force-recreate",
        action="store_true",
        help="Delete invalid scale dataset and recreate from scratch.",
    )
    p.add_argument(
        "--skip-execute",
        action="store_true",
        help="Seed only, do not execute batch runs.",
    )
    p.add_argument(
        "--strict",
        action="store_true",
        help="Exit code 1 if any run fails or counts don't match.",
    )
    return p.parse_args()


async def _force_recreate_dataset(session) -> None:
    """Delete the scale dataset and all dependent rows so seeding can restart clean."""
    ds = (
        await session.execute(
            select(Dataset).where(Dataset.name == SCALE_DATASET_NAME).limit(1)
        )
    ).scalar_one_or_none()
    if ds is None:
        print(f"  No dataset named {SCALE_DATASET_NAME!r} found — nothing to delete.")
        return
    # Runs depend on query_cases which depend on dataset — cascade handles the rest
    qc_ids = [
        r.id
        for r in (
            await session.execute(
                select(QueryCase).where(QueryCase.dataset_id == ds.id)
            )
        ).scalars().all()
    ]
    if qc_ids:
        # Delete runs first (cascade should handle retrieval/eval/gen results)
        await session.execute(
            delete(Run).where(Run.query_case_id.in_(qc_ids))
        )
        await session.execute(
            delete(QueryCase).where(QueryCase.dataset_id == ds.id)
        )
    await session.delete(ds)
    await session.commit()
    print(f"  Deleted dataset {SCALE_DATASET_NAME!r} (id={ds.id}), {len(qc_ids)} query cases, and all dependent runs.")


async def _seed(session, *, force_recreate: bool) -> ScaleBenchmarkSeedResult:
    """Seed the scale benchmark, with optional force-recreate on mismatch."""
    if force_recreate:
        print("[1/4] Force-recreating scale benchmark dataset...")
        await _force_recreate_dataset(session)
    else:
        print("[1/4] Seeding scale benchmark (idempotent)...")

    try:
        result = await ensure_scale_benchmark_ready(session)
    except ValueError as exc:
        if not force_recreate and "query cases" in str(exc):
            print(f"  ERROR: {exc}")
            print("  → Re-run with --force-recreate to delete the invalid dataset and rebuild.")
            raise SystemExit(1) from exc
        raise

    print(f"  Dataset ID:        {result.dataset_id}")
    print(f"  Query cases:       {len(result.query_case_ids)}")
    print(f"  Pipeline configs:  {list(result.pipeline_config_ids)}")
    print(f"  Document ID:       {result.document_id}")
    return result


async def _execute_batch(
    session,
    seed: ScaleBenchmarkSeedResult,
    reps: int,
) -> dict:
    """Execute the traced heuristic batch."""
    n_queries = len(seed.query_case_ids)
    n_configs = len(seed.pipeline_config_ids)
    expected_runs = n_queries * n_configs * reps

    print(f"\n[2/4] Executing batch: {n_queries} queries × {n_configs} configs × {reps} reps = {expected_runs} runs...")
    t0 = time.perf_counter()

    result = await run_batch_benchmark(
        session,
        [seed.dataset_id],
        list(seed.pipeline_config_ids),
        n_queries,
        reps,
        "heuristic",
        document_id=seed.document_id,
        experiment_name="scale_evidence_pipeline",
        commit=True,
    )

    elapsed = time.perf_counter() - t0
    print(f"  Batch ID:     {result.batch_id}")
    print(f"  Total runs:   {result.total_runs}")
    print(f"  Successes:    {result.successes}")
    print(f"  Failures:     {result.failures}")
    print(f"  Success rate: {result.success_rate:.1%}")
    print(f"  Elapsed:      {elapsed:.1f}s")

    return {
        "batch_id": result.batch_id,
        "total_runs": result.total_runs,
        "successes": result.successes,
        "failures": result.failures,
        "success_rate": result.success_rate,
        "elapsed_sec": round(elapsed, 1),
        "expected_runs": expected_runs,
    }


async def _verify_dashboard_counts(session, dataset_id: int) -> dict:
    """Query the DB directly for dashboard-relevant counts."""
    from app.domain.dashboard_dataset_scope import dashboard_aggregate_run_scope

    run_scope = dashboard_aggregate_run_scope(Run, dataset_id)

    total_runs = int(
        await session.scalar(
            select(func.count()).select_from(Run).where(run_scope)
        ) or 0
    )
    unique_queries = int(
        await session.scalar(
            select(func.count(func.distinct(Run.query_case_id)))
            .select_from(Run).where(run_scope)
        ) or 0
    )
    traced_runs = int(
        await session.scalar(
            select(func.count())
            .select_from(Run)
            .where(
                run_scope,
                Run.id.in_(
                    select(EvaluationResult.run_id)
                ),
            )
        ) or 0
    )
    configs_tested = int(
        await session.scalar(
            select(func.count(func.distinct(Run.pipeline_config_id)))
            .select_from(Run).where(run_scope)
        ) or 0
    )

    return {
        "total_runs": total_runs,
        "unique_query_cases_with_runs": unique_queries,
        "total_traced_runs": traced_runs,
        "configs_tested": configs_tested,
    }


async def _main() -> int:
    ns = _parse_args()

    async with async_session_maker() as session:
        # Step 1: Seed
        seed = await _seed(session, force_recreate=ns.force_recreate)

        if ns.skip_execute:
            print("\n[2/4] Skipping batch execution (--skip-execute).")
            print("\n[3/4] Skipping verification.")
            print("\n[4/4] Done (seed only).")
            return 0

        # Step 2: Execute
        batch = await _execute_batch(session, seed, ns.reps)

    # Step 3: Verify (fresh session to see committed data)
    async with async_session_maker() as session:
        print(f"\n[3/4] Verifying dashboard counts for dataset {seed.dataset_id}...")
        counts = await _verify_dashboard_counts(session, seed.dataset_id)

    print(f"  Total runs in dataset:              {counts['total_runs']}")
    print(f"  Unique query cases with runs:       {counts['unique_query_cases_with_runs']}")
    print(f"  Total traced runs (with eval):      {counts['total_traced_runs']}")
    print(f"  Configs tested:                     {counts['configs_tested']}")

    # Step 4: Evidence report
    print("\n[4/4] Evidence report:")
    print("=" * 60)

    all_ok = True
    expected = batch["expected_runs"]

    if counts["total_traced_runs"] >= 200:
        print(f"  ✓ 200+ traced runs: {counts['total_traced_runs']} (target: 200+)")
    else:
        print(f"  ✗ Traced runs below 200: {counts['total_traced_runs']} (need more reps)")
        all_ok = False

    if counts["unique_query_cases_with_runs"] == 52:
        print(f"  ✓ 52 unique query cases: {counts['unique_query_cases_with_runs']}")
    else:
        print(f"  ✗ Unique queries: {counts['unique_query_cases_with_runs']} (expected 52)")
        all_ok = False

    if counts["configs_tested"] >= 2:
        print(f"  ✓ {counts['configs_tested']} configs tested")
    else:
        print(f"  ✗ Configs: {counts['configs_tested']} (expected ≥2)")
        all_ok = False

    if batch["failures"] == 0:
        print(f"  ✓ Zero pipeline failures")
    else:
        print(f"  ✗ {batch['failures']} pipeline failures in batch")
        all_ok = False

    print("=" * 60)

    if all_ok:
        print("\n  EVIDENCE-SAFE WORDING:")
        print(f"  \"Executed {counts['total_traced_runs']} traced benchmark runs across")
        print(f"   {counts['unique_query_cases_with_runs']} unique queries and {counts['configs_tested']} pipeline configurations,")
        print(f"   with structured failure taxonomy and per-run trace instrumentation.\"")
    else:
        print("\n  NOT YET EVIDENCE-SAFE — see failures above.")

    print(
        "\n  Full evidence JSON:",
        json.dumps(
            {**batch, "dashboard_counts": counts, "evidence_safe": all_ok},
            indent=2,
        ),
    )

    if ns.strict and not all_ok:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
