"""Honest dashboard add-ons: diagnosis timing + matched LLM-judge reduction (from persisted rows)."""

from __future__ import annotations

import statistics
from collections import defaultdict
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.dashboard_dataset_scope import dashboard_aggregate_run_scope
from app.models import DiagnosisTimingSession, EvaluationResult, GenerationResult, QueryCase, Run
from app.schemas.dashboard_summary import (
    DashboardDiagnosisTimingEvidence,
    DashboardLlmReductionEvidence,
    DashboardLlmReductionWorkloadRow,
)


def _median_seconds(durations: list[float]) -> float | None:
    if not durations:
        return None
    return float(statistics.median(durations))


def _diagnosis_tier(
    *,
    manual_n: int,
    assisted_n: int,
) -> tuple[Literal["insufficient", "limited", "normal"], str]:
    if manual_n < 5 or assisted_n < 5:
        return (
            "insufficient",
            "Fewer than 5 completed sessions in one or both modes — insufficient evidence.",
        )
    if manual_n < 10 or assisted_n < 10:
        return (
            "limited",
            "Between 5 and 9 completed sessions in one or both modes — directional evidence only.",
        )
    return ("normal", "")


def _llm_reduction_tier(n_pairs: int) -> tuple[Literal["sparse", "directional", "normal"], str]:
    if n_pairs < 3:
        return ("sparse", "Fewer than 3 matched workload arms — not meaningful.")
    if n_pairs < 10:
        return ("directional", "Between 3 and 9 matched runs per arm — directional only.")
    return ("normal", "")


async def build_diagnosis_timing_evidence(
    session: AsyncSession,
    *,
    dataset_id: int | None,
) -> DashboardDiagnosisTimingEvidence:
    run_scope = dashboard_aggregate_run_scope(Run, dataset_id)
    stmt = (
        select(DiagnosisTimingSession)
        .join(Run, Run.id == DiagnosisTimingSession.run_id)
        .where(run_scope, DiagnosisTimingSession.synthetic.is_(False))
    )
    rows = list((await session.execute(stmt)).scalars().all())

    def completed_durations(mode: str) -> list[float]:
        out: list[float] = []
        for r in rows:
            if r.mode != mode or r.completed_at is None:
                continue
            delta = (r.completed_at - r.started_at).total_seconds()
            if delta >= 0:
                out.append(delta)
        return out

    def insight_durations(mode: str) -> list[float]:
        out: list[float] = []
        for r in rows:
            if r.mode != mode or r.first_meaningful_insight_at is None:
                continue
            delta = (r.first_meaningful_insight_at - r.started_at).total_seconds()
            if delta >= 0:
                out.append(delta)
        return out

    manual_d = completed_durations("manual")
    assisted_d = completed_durations("assisted")
    manual_i = insight_durations("manual")
    assisted_i = insight_durations("assisted")

    tier, tier_note = _diagnosis_tier(
        manual_n=len(manual_d),
        assisted_n=len(assisted_d),
    )

    med_m = _median_seconds(manual_d)
    med_a = _median_seconds(assisted_d)
    delta_sec = None
    pct_reduction = None
    if med_m is not None and med_m > 0 and med_a is not None:
        delta_sec = med_m - med_a
        pct_reduction = (delta_sec / med_m) * 100.0

    return DashboardDiagnosisTimingEvidence(
        sessions_count=len(rows),
        manual_completed_sessions=len(manual_d),
        assisted_completed_sessions=len(assisted_d),
        median_diagnosis_duration_sec_manual=med_m,
        median_diagnosis_duration_sec_assisted=med_a,
        median_time_to_first_insight_sec_manual=_median_seconds(manual_i),
        median_time_to_first_insight_sec_assisted=_median_seconds(assisted_i),
        median_delta_sec_assisted_vs_manual=delta_sec,
        percent_reduction_vs_manual=pct_reduction,
        evidence_tier=tier,
        evidence_tier_note=tier_note or None,
        framework_note=(
            "Diagnosis timing is measured from persisted sessions only; "
            "no default or fabricated improvement is shown."
        ),
    )


def _arm_judge_used(instr: dict[str, Any] | None) -> int | None:
    if not instr:
        return None
    v = instr.get("llm_judge_calls_used_for_final_judgment")
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


async def build_llm_reduction_evidence(
    session: AsyncSession,
    *,
    dataset_id: int | None,
) -> DashboardLlmReductionEvidence:
    """Compare matched workloads where metadata tags both llm_only and hybrid arms."""

    run_scope = dashboard_aggregate_run_scope(Run, dataset_id)
    stmt = (
        select(Run, QueryCase.dataset_id)
        .join(QueryCase, QueryCase.id == Run.query_case_id)
        .join(EvaluationResult, EvaluationResult.run_id == Run.id)
        .join(GenerationResult, GenerationResult.run_id == Run.id)
        .where(
            run_scope,
            Run.trace_instrumentation_json.isnot(None),
        )
    )
    exec_rows = (await session.execute(stmt)).all()

    # workload_id -> arm -> list judge used (0 or 1)
    buckets: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))
    workload_dataset: dict[str, int] = {}

    for run, ds in exec_rows:
        meta = run.metadata_json or {}
        wid = meta.get("matched_llm_reduction_workload_id")
        arm = meta.get("matched_llm_reduction_arm")
        if not wid or arm not in ("llm_only", "hybrid"):
            continue
        if isinstance(wid, str) and wid.strip():
            wkey = wid.strip()
        else:
            continue
        used = _arm_judge_used(run.trace_instrumentation_json)
        if used is None:
            continue
        buckets[wkey][str(arm)].append(used)
        workload_dataset[wkey] = int(ds)

    workloads: list[DashboardLlmReductionWorkloadRow] = []
    reductions: list[float] = []

    for wid, arms in buckets.items():
        lo = arms.get("llm_only") or []
        hy = arms.get("hybrid") or []
        if not lo or not hy:
            continue
        avg_lo = sum(lo) / len(lo)
        avg_hy = sum(hy) / len(hy)
        if avg_lo <= 0:
            continue
        pct = (avg_lo - avg_hy) / avg_lo * 100.0
        reductions.append(pct)
        workloads.append(
            DashboardLlmReductionWorkloadRow(
                matched_workload_id=wid,
                dataset_id=workload_dataset.get(wid),
                llm_only_runs=len(lo),
                hybrid_runs=len(hy),
                avg_llm_judge_calls_llm_only=round(avg_lo, 4),
                avg_llm_judge_calls_hybrid=round(avg_hy, 4),
                llm_judge_reduction_pct=round(pct, 4),
            )
        )

    total_lo = sum(w.llm_only_runs for w in workloads)
    total_hy = sum(w.hybrid_runs for w in workloads)
    sample_for_gate = min(total_lo, total_hy) if workloads else 0

    tier, tier_note = _llm_reduction_tier(sample_for_gate)

    overall_pct = float(statistics.median(reductions)) if reductions else None

    return DashboardLlmReductionEvidence(
        matched_workloads=workloads,
        workload_count=len(workloads),
        median_llm_judge_reduction_pct_across_workloads=overall_pct,
        evidence_tier=tier,
        evidence_tier_note=tier_note,
        validity_note=(
            "Reductions apply only to runs tagged with matched_llm_reduction_workload_id "
            "and matched_llm_reduction_arm in {llm_only, hybrid}, with generation + evaluation "
            "and trace_instrumentation_json present."
        ),
    )