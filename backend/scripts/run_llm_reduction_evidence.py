#!/usr/bin/env python3
"""Generate matched LLM-only vs hybrid evidence for LLM judge call reduction.

Usage::

    python scripts/run_llm_reduction_evidence.py
    python scripts/run_llm_reduction_evidence.py --workloads 5 --queries 10 --reps 2

Requires:
  - ``alembic upgrade head``
  - ``seed_scale_benchmark.py`` already run (or this seeds automatically)
  - ``OPENAI_API_KEY`` (or provider key) set for LLM generation + judge

Each workload creates matched llm_only + hybrid arms with the same workload UUID.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.config import settings  # noqa: E402
from app.database import async_session_maker  # noqa: E402
from app.services.batch_runner import run_batch_benchmark  # noqa: E402
from app.services.benchmark_scale_seed import ensure_scale_benchmark_ready  # noqa: E402
from app.services.dashboard_evidence import build_llm_reduction_evidence  # noqa: E402


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Generate matched LLM vs hybrid workload evidence."
    )
    p.add_argument(
        "--workloads",
        type=int,
        default=3,
        help="Number of matched workload pairs to generate (default 3 → directional tier).",
    )
    p.add_argument(
        "--queries",
        type=int,
        default=5,
        help="Queries per workload arm (default 5).",
    )
    p.add_argument(
        "--reps",
        type=int,
        default=1,
        help="Reps per query per arm (default 1).",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be executed without running.",
    )
    return p.parse_args()


def _check_api_key() -> str | None:
    """Check for the provider API key. Returns error message or None."""
    provider = getattr(settings, "llm_provider", "openai")
    if provider == "anthropic":
        key = getattr(settings, "claude_api_key", None)
        if not key:
            return "CLAUDE_API_KEY not set. Required for LLM judge calls (LLM_PROVIDER=anthropic)."
    else:
        key = getattr(settings, "openai_api_key", None)
        if not key:
            return "OPENAI_API_KEY not set. Required for LLM generation + judge calls."
    return None


async def _main() -> int:
    ns = _parse_args()

    # Pre-flight: API key check
    key_err = _check_api_key()
    if key_err:
        print(f"ERROR: {key_err}")
        print("  → Export the API key before running this script.")
        print("  → Example: export OPENAI_API_KEY=sk-...")
        return 1

    print(f"[1/5] Seeding scale benchmark...")
    async with async_session_maker() as session:
        seed = await ensure_scale_benchmark_ready(session)

    d = seed.dataset_id
    c1 = seed.pipeline_config_ids[0]
    doc = seed.document_id

    print(f"  Dataset: {d}, Config: {c1}, Document: {doc}")
    print(f"\n[2/5] Planning {ns.workloads} matched workloads ({ns.queries} queries × {ns.reps} reps each arm)...")

    workload_ids = [str(uuid.uuid4()) for _ in range(ns.workloads)]
    total_runs_per_arm = ns.workloads * ns.queries * ns.reps
    total_runs = total_runs_per_arm * 2

    print(f"  Workload UUIDs: {len(workload_ids)}")
    print(f"  Runs per arm:   {total_runs_per_arm}")
    print(f"  Total runs:     {total_runs}")

    if ns.dry_run:
        print("\n  DRY RUN — commands that would execute:")
        for i, wid in enumerate(workload_ids):
            print(f"\n  Workload {i+1}/{ns.workloads} ({wid[:8]}...):")
            print(f"    ARM llm_only:  run_batch_benchmark -d {d} -c {c1} -q {ns.queries} -r {ns.reps} -e llm --document-id {doc} --matched-llm-reduction-workload-id {wid}")
            print(f"    ARM hybrid:    run_batch_benchmark -d {d} -c {c1} -q {ns.queries} -r {ns.reps} -e llm_hybrid --document-id {doc} --matched-llm-reduction-workload-id {wid}")
        return 0

    print(f"\n[3/5] Executing workload arms (this calls the LLM — may take a while)...")

    successes = 0
    failures = 0

    for i, wid in enumerate(workload_ids):
        print(f"\n  --- Workload {i+1}/{ns.workloads} ({wid[:8]}...) ---")

        for arm, evaluator in [("llm_only", "llm"), ("hybrid", "llm_hybrid")]:
            print(f"    ARM {arm}: ", end="", flush=True)
            try:
                async with async_session_maker() as session:
                    result = await run_batch_benchmark(
                        session,
                        [d],
                        [c1],
                        ns.queries,
                        ns.reps,
                        evaluator,
                        document_id=doc,
                        experiment_name=f"llm_reduction_evidence_{arm}",
                        matched_llm_reduction_workload_id=wid,
                        commit=True,
                    )
                print(f"{result.successes}/{result.total_runs} succeeded")
                successes += result.successes
                failures += result.failures
            except Exception as exc:
                print(f"FAILED — {exc}")
                failures += ns.queries * ns.reps

    print(f"\n[4/5] Querying dashboard for reduction evidence...")
    async with async_session_maker() as session:
        evidence = await build_llm_reduction_evidence(session, dataset_id=d)

    print(f"  Matched workloads found:   {evidence.workload_count}")
    print(f"  Evidence tier:             {evidence.evidence_tier}")
    if evidence.evidence_tier_note:
        print(f"  Tier note:                 {evidence.evidence_tier_note}")
    if evidence.median_llm_judge_reduction_pct_across_workloads is not None:
        print(f"  Median reduction:          {evidence.median_llm_judge_reduction_pct_across_workloads:.1f}%")

    for w in evidence.matched_workloads:
        print(f"    Workload {w.matched_workload_id[:8]}...: "
              f"llm_only={w.llm_only_runs} runs (avg {w.avg_llm_judge_calls_llm_only:.2f} calls), "
              f"hybrid={w.hybrid_runs} runs (avg {w.avg_llm_judge_calls_hybrid:.2f} calls) "
              f"→ {w.llm_judge_reduction_pct:.1f}% reduction")

    print(f"\n[5/5] Evidence report:")
    print("=" * 60)

    is_safe = evidence.evidence_tier in ("directional", "normal")

    if evidence.evidence_tier == "normal":
        print(f"  ✓ NORMAL tier: {evidence.workload_count} workloads, ≥10 matched runs per arm")
    elif evidence.evidence_tier == "directional":
        print(f"  ~ DIRECTIONAL tier: {evidence.workload_count} workloads (3-9 matched runs)")
    else:
        print(f"  ✗ SPARSE tier: insufficient matched workload data")

    if is_safe and evidence.median_llm_judge_reduction_pct_across_workloads is not None:
        pct = evidence.median_llm_judge_reduction_pct_across_workloads
        tier_word = "directional" if evidence.evidence_tier == "directional" else "measured"
        print(f"\n  EVIDENCE-SAFE WORDING ({tier_word}):")
        print(f"  \"Hybrid evaluation gate achieved {pct:.0f}% median LLM judge call reduction")
        print(f"   across {evidence.workload_count} matched workloads ({tier_word} evidence).\"")
    else:
        print(f"\n  NOT YET EVIDENCE-SAFE — need more matched workloads.")

    print("=" * 60)

    report = {
        "total_successes": successes,
        "total_failures": failures,
        "workload_count": evidence.workload_count,
        "evidence_tier": evidence.evidence_tier,
        "median_reduction_pct": evidence.median_llm_judge_reduction_pct_across_workloads,
        "evidence_safe": is_safe,
    }
    print(f"\n  Full evidence JSON: {json.dumps(report, indent=2)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
