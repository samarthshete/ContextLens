#!/usr/bin/env python3
"""Diagnosis timing experiment: candidate selection, balanced plan, and export.

Usage::

    # Ranked candidate list (default)
    python scripts/list_diagnosis_candidates.py

    # Grouped by experiment bucket
    python scripts/list_diagnosis_candidates.py --view buckets

    # Balanced 20-run experiment plan
    python scripts/list_diagnosis_candidates.py --view plan

    # Export experiment plan as CSV
    python scripts/list_diagnosis_candidates.py --view plan --export-plan plan.csv

    # Export experiment plan as JSON
    python scripts/list_diagnosis_candidates.py --view plan --export-plan plan.json

    # Export existing sessions (unchanged from before)
    python scripts/list_diagnosis_candidates.py --export-sessions

    # Scope to a specific dataset
    python scripts/list_diagnosis_candidates.py --dataset-id 42 --view plan
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import io
import json
import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from sqlalchemy import func, select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.database import async_session_maker  # noqa: E402
from app.models import (  # noqa: E402
    DiagnosisTimingSession,
    EvaluationResult,
    QueryCase,
    Run,
)
from app.services.dashboard_evidence import build_diagnosis_timing_evidence  # noqa: E402
from app.services.diagnosis_experiment_design import (  # noqa: E402
    ALL_BUCKETS,
    CandidateRun,
    ExperimentPlan,
    GROUP_TARGETS,
    build_experiment_plan,
    classify_bucket,
    compute_difficulty,
    format_bucket_summary,
    format_experiment_plan,
    plan_to_export_rows,
    score_candidates,
)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Diagnosis timing experiment: candidate selection + balanced experiment plan.",
    )
    p.add_argument("--dataset-id", type=int, default=None, help="Scope to dataset")
    p.add_argument(
        "--limit", type=int, default=200,
        help="Max candidate runs to fetch from DB (default: 200)",
    )
    p.add_argument(
        "--view",
        choices=["candidates", "buckets", "plan"],
        default="candidates",
        help="Output view: ranked candidates, bucketed view, or balanced experiment plan",
    )
    p.add_argument("--export-sessions", action="store_true", help="Export existing sessions as CSV")
    p.add_argument("--export-file", default=None, help="CSV output path for --export-sessions")
    p.add_argument(
        "--export-plan", default=None,
        help="Export experiment plan to file (.csv or .json)",
    )
    return p.parse_args()


# ---------------------------------------------------------------------------
# DB → CandidateRun list
# ---------------------------------------------------------------------------


async def _fetch_candidates(
    session: AsyncSession,
    dataset_id: int | None,
    limit: int,
) -> list[CandidateRun]:
    """Fetch completed runs with evaluation results as CandidateRun structs."""
    stmt = (
        select(Run, EvaluationResult, QueryCase)
        .join(EvaluationResult, EvaluationResult.run_id == Run.id)
        .join(QueryCase, QueryCase.id == Run.query_case_id)
        .where(Run.status == "completed")
    )
    if dataset_id is not None:
        stmt = stmt.where(QueryCase.dataset_id == dataset_id)

    # Fetch a large pool — scoring will rank them
    stmt = stmt.order_by(Run.id.desc()).limit(limit)
    rows = (await session.execute(stmt)).all()

    # Fetch existing session counts
    run_ids = [r.id for r, _, _ in rows]
    existing_sessions: dict[int, dict[str, int]] = {}
    if run_ids:
        session_counts = (
            await session.execute(
                select(
                    DiagnosisTimingSession.run_id,
                    DiagnosisTimingSession.mode,
                    func.count().label("cnt"),
                )
                .where(
                    DiagnosisTimingSession.run_id.in_(run_ids),
                    DiagnosisTimingSession.synthetic.is_(False),
                )
                .group_by(DiagnosisTimingSession.run_id, DiagnosisTimingSession.mode)
            )
        ).all()
        for run_id, mode, cnt in session_counts:
            existing_sessions.setdefault(run_id, {})[mode] = cnt

    candidates: list[CandidateRun] = []
    for run, ev, qc in rows:
        sessions = existing_sessions.get(run.id, {})
        candidates.append(CandidateRun(
            run_id=run.id,
            failure_type=ev.failure_type or "NO_FAILURE",
            query_text=qc.query_text or "",
            query_case_id=qc.id,
            dataset_id=qc.dataset_id,
            retrieval_relevance=ev.retrieval_relevance,
            context_coverage=ev.context_coverage,
            completeness=ev.completeness,
            faithfulness=ev.faithfulness,
            manual_sessions=sessions.get("manual", 0),
            assisted_sessions=sessions.get("assisted", 0),
        ))

    return candidates


# ---------------------------------------------------------------------------
# View: ranked candidate list
# ---------------------------------------------------------------------------


def _print_candidates(scored_candidates, dataset_id: int | None) -> None:
    """Print scored + bucketed candidate list."""
    print(f"\nDiagnosis experiment candidates (dataset_id={dataset_id or 'all'}):")
    print(f"  Scored and ranked by experiment value. Higher score = better candidate.\n")

    print(
        f"  {'#':>3} {'Run ID':>8} {'Score':>7} {'Bucket':<25} {'Failure Type':<22} "
        f"{'M':>3} {'A':>3} {'Query (truncated)':<40}"
    )
    print("  " + "-" * 118)

    for i, sc in enumerate(scored_candidates[:50], 1):
        c = sc.candidate
        qt = c.query_text[:38] if c.query_text else ""
        print(
            f"  {i:>3} {c.run_id:>8} {sc.score:>7.1f} {sc.bucket:<25} "
            f"{c.failure_type:<22} {c.manual_sessions:>3} {c.assisted_sessions:>3} {qt:<40}"
        )

    # Summary
    bucket_counts: dict[str, int] = {}
    for sc in scored_candidates:
        bucket_counts[sc.bucket] = bucket_counts.get(sc.bucket, 0) + 1

    print(f"\n  Total candidates: {len(scored_candidates)}")
    print(f"  Bucket distribution:")
    for b in ALL_BUCKETS:
        print(f"    {b:<25} {bucket_counts.get(b, 0):>5}")


# ---------------------------------------------------------------------------
# View: bucketed
# ---------------------------------------------------------------------------


def _print_buckets(scored_candidates, dataset_id: int | None) -> None:
    """Print candidates grouped by bucket."""
    print(f"\nDiagnosis candidates by bucket (dataset_id={dataset_id or 'all'}):")

    buckets: dict[str, list] = {b: [] for b in ALL_BUCKETS}
    for sc in scored_candidates:
        buckets[sc.bucket].append(sc)

    for bucket in ALL_BUCKETS:
        pool = buckets[bucket]
        needed = 2 * GROUP_TARGETS.get(bucket, 0)
        status = "✓" if len(pool) >= needed else f"✗ (need {needed}, have {len(pool)})"

        print(f"\n  [{bucket.upper()}] — {len(pool)} candidates — {status}")
        print(
            f"    {'Run ID':>8} {'Score':>7} {'Failure Type':<22} {'Diff':>5} "
            f"{'M':>3} {'A':>3} {'Query':<38}"
        )
        print("    " + "-" * 95)

        for sc in pool[:10]:  # Show top 10 per bucket
            c = sc.candidate
            diff = compute_difficulty(c)
            qt = c.query_text[:36] if c.query_text else ""
            print(
                f"    {c.run_id:>8} {sc.score:>7.1f} {c.failure_type:<22} {diff:>5.2f} "
                f"{c.manual_sessions:>3} {c.assisted_sessions:>3} {qt:<38}"
            )
        if len(pool) > 10:
            print(f"    ... and {len(pool) - 10} more")


# ---------------------------------------------------------------------------
# View: balanced experiment plan
# ---------------------------------------------------------------------------


def _print_plan(plan: ExperimentPlan) -> None:
    """Print the full balanced experiment plan."""
    print(format_experiment_plan(plan))

    # Execution instructions
    print("\n" + "=" * 80)
    print("HOW TO EXECUTE THIS EXPERIMENT:")
    print("=" * 80)
    print("""
For each run in the MANUAL group:
  1. Open /runs/<run_id> in the UI
  2. In the 'Diagnosis timing experiment' panel, select MANUAL
  3. Click 'Start session'
  4. Diagnose the run WITHOUT assisted widgets (they will be hidden)
  5. When you first understand the root cause, click 'Mark first insight'
  6. When you can fully explain the failure, click 'Mark completed'

For each run in the ASSISTED group:
  1. Open /runs/<run_id> in the UI
  2. Select ASSISTED mode
  3. Click 'Start session'
  4. Use the diagnosis widgets normally
  5. Mark 'first insight' and 'completed' as above

IMPORTANT:
  • Do all MANUAL sessions first (or randomise order), to avoid learning effects
  • Keep timing behaviour consistent — do not rush clicks for better numbers
  • You need ≥10 completed sessions per mode for 'normal' evidence tier
  • The plan pairs similar-difficulty runs across groups for fair comparison
""")


# ---------------------------------------------------------------------------
# Plan export
# ---------------------------------------------------------------------------


def _export_plan(plan: ExperimentPlan, path: str) -> None:
    """Export experiment plan as CSV or JSON."""
    rows = plan_to_export_rows(plan)

    if path.endswith(".json"):
        output = {
            "experiment_plan": rows,
            "warnings": plan.warnings,
            "bucket_summary": {
                b: plan.bucket_summary[b] for b in ALL_BUCKETS
            },
        }
        Path(path).write_text(json.dumps(output, indent=2))
        print(f"Exported plan ({len(rows)} slots) to {path}")
    else:
        # CSV
        sio = io.StringIO()
        if rows:
            writer = csv.DictWriter(sio, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
        Path(path).write_text(sio.getvalue())
        print(f"Exported plan ({len(rows)} slots) to {path}")


# ---------------------------------------------------------------------------
# Session export (preserved from original)
# ---------------------------------------------------------------------------


async def _export_sessions(
    session: AsyncSession,
    dataset_id: int | None,
    export_file: str | None,
) -> None:
    """Export non-synthetic diagnosis timing sessions as CSV."""
    stmt = (
        select(DiagnosisTimingSession, Run.query_case_id)
        .join(Run, Run.id == DiagnosisTimingSession.run_id)
        .where(DiagnosisTimingSession.synthetic.is_(False))
    )
    if dataset_id is not None:
        stmt = stmt.join(QueryCase, QueryCase.id == Run.query_case_id).where(
            QueryCase.dataset_id == dataset_id
        )
    stmt = stmt.order_by(DiagnosisTimingSession.id.asc())

    rows = (await session.execute(stmt)).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "session_id", "run_id", "query_case_id", "mode",
        "started_at", "first_meaningful_insight_at", "completed_at",
        "duration_sec", "time_to_first_insight_sec",
        "resolution_label", "notes",
    ])

    for s, qc_id in rows:
        dur = None
        if s.completed_at and s.started_at:
            dur = round((s.completed_at - s.started_at).total_seconds(), 2)
        ttfi = None
        if s.first_meaningful_insight_at and s.started_at:
            ttfi = round((s.first_meaningful_insight_at - s.started_at).total_seconds(), 2)

        writer.writerow([
            s.id, s.run_id, qc_id, s.mode,
            s.started_at.isoformat() if s.started_at else "",
            s.first_meaningful_insight_at.isoformat() if s.first_meaningful_insight_at else "",
            s.completed_at.isoformat() if s.completed_at else "",
            dur, ttfi,
            s.resolution_label or "", s.notes or "",
        ])

    csv_text = output.getvalue()

    if export_file:
        Path(export_file).write_text(csv_text)
        print(f"Exported {len(rows)} sessions to {export_file}")
    else:
        print(csv_text)

    # Evidence summary
    evidence = await build_diagnosis_timing_evidence(session, dataset_id=dataset_id)
    print(f"\nEvidence summary:")
    print(f"  Total non-synthetic sessions:    {evidence.sessions_count}")
    print(f"  Manual completed:                {evidence.manual_completed_sessions}")
    print(f"  Assisted completed:              {evidence.assisted_completed_sessions}")
    print(f"  Evidence tier:                   {evidence.evidence_tier}")
    if evidence.median_diagnosis_duration_sec_manual is not None:
        print(f"  Median manual duration:          {evidence.median_diagnosis_duration_sec_manual:.1f}s")
    if evidence.median_diagnosis_duration_sec_assisted is not None:
        print(f"  Median assisted duration:         {evidence.median_diagnosis_duration_sec_assisted:.1f}s")
    if evidence.percent_reduction_vs_manual is not None:
        print(f"  Reduction vs manual:             {evidence.percent_reduction_vs_manual:.1f}%")

    if evidence.evidence_tier == "insufficient":
        needed_m = max(0, 5 - evidence.manual_completed_sessions)
        needed_a = max(0, 5 - evidence.assisted_completed_sessions)
        print(f"\n  → Need {needed_m} more manual + {needed_a} more assisted for 'limited' tier")
        print(f"  → Need {max(0, 10 - evidence.manual_completed_sessions)} more manual + "
              f"{max(0, 10 - evidence.assisted_completed_sessions)} more assisted for 'normal' tier")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def _main() -> int:
    ns = _parse_args()

    async with async_session_maker() as session:
        if ns.export_sessions:
            await _export_sessions(session, ns.dataset_id, ns.export_file)
            return 0

        # Fetch and score candidates
        candidates = await _fetch_candidates(session, ns.dataset_id, ns.limit)

        if not candidates:
            print("\nNo completed runs with evaluation results found.")
            print("Seed and run benchmarks first, for example:")
            print("  python scripts/seed_scale_benchmark.py")
            print("  python scripts/run_scale_evidence_pipeline.py")
            print("Or: python scripts/seed_benchmark.py && python scripts/run_benchmark.py --eval-mode heuristic")
            return 1

        scored = score_candidates(candidates)

        if ns.view == "candidates":
            _print_candidates(scored, ns.dataset_id)
        elif ns.view == "buckets":
            _print_buckets(scored, ns.dataset_id)
        elif ns.view == "plan":
            plan = build_experiment_plan(scored)
            _print_plan(plan)

            if ns.export_plan:
                _export_plan(plan, ns.export_plan)

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
