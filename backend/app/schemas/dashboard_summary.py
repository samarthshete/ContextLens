"""Response for ``GET /api/v1/runs/dashboard-summary`` — operator / demo metrics."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class DashboardStatusCounts(BaseModel):
    """Run row counts by lifecycle (``runs.status``)."""

    completed: int = 0
    failed: int = 0
    in_progress: int = 0
    """Not ``completed`` or ``failed`` (e.g. ``pending``, ``running``, mid-pipeline)."""


class DashboardScaleMetrics(BaseModel):
    """Inventory and traced-run scale from canonical tables (read-only ``COUNT`` / ``COUNT DISTINCT``).

    Aligns with ``app/metrics/aggregate.py`` where the same names exist, plus corpus-focused counts.
    Integer **0** is a valid measured value (empty table); there is no separate N/A for counts.
    """

    benchmark_datasets: int = 0
    """Rows in ``datasets``."""
    total_queries: int = 0
    """Rows in ``query_cases``."""
    total_traced_runs: int = 0
    """Runs with ≥1 ``evaluation_results`` row (dashboard slice; ``aggregate.py`` may use stricter retrieval+eval)."""
    configs_tested: int = 0
    """``COUNT(DISTINCT runs.pipeline_config_id)`` over all run rows (same as metrics aggregate)."""
    documents_processed: int = 0
    """Documents with ``status == 'processed'`` (successful ingest per upload pipeline)."""
    chunks_indexed: int = 0
    """Rows in ``chunks`` (stored chunk records; cascade with documents)."""
    unique_query_cases_with_runs: int = 0
    """``COUNT(DISTINCT query_case_id)`` over runs in the active dashboard scope."""


class DashboardEvaluatorCounts(BaseModel):
    """Distinct runs with an evaluation row in each bucket (see ``evaluator_bucket``)."""

    heuristic_runs: int = 0
    llm_runs: int = 0
    runs_without_evaluation: int = 0


class DashboardLatencySummary(BaseModel):
    """Latency over ``runs`` where each column IS NOT NULL.

    Means are arithmetic averages. Retrieval P50/P95 use PostgreSQL ``percentile_cont``
    over the same non-null ``retrieval_latency_ms`` rows as the mean (see
    ``phase_latency_distribution``).

    ``avg_total_latency_ms``, ``total_latency_p50_ms``, and ``end_to_end_run_latency_*_sec`` use the
    same non-null ``runs.total_latency_ms`` population (mean + ``percentile_cont(0.5/0.95)``); seconds
    are milliseconds / 1000. ``None`` = insufficient data (no samples).
    """

    avg_retrieval_latency_ms: float | None = None
    retrieval_latency_p50_ms: float | None = None
    retrieval_latency_p95_ms: float | None = None
    avg_generation_latency_ms: float | None = None
    avg_evaluation_latency_ms: float | None = None
    avg_total_latency_ms: float | None = None
    total_latency_p50_ms: float | None = None
    end_to_end_run_latency_avg_sec: float | None = None
    end_to_end_run_latency_p50_sec: float | None = None
    end_to_end_run_latency_p95_sec: float | None = None


class DashboardCostSummary(BaseModel):
    """From ``evaluation_results.cost_usd`` only — aligns with trace cost semantics (NULL = N/A).

    **Heuristic** evaluations do not record LLM USD; averages below are **LLM-bucket rows only**
    (see ``evaluator_bucket``). **Full RAG** = run has a ``generation_results`` row (benchmark
    ``eval_mode=full`` path). **Per-run** fields group by ``run_id`` first (``SUM`` then ``AVG``)
    so multiple evaluation rows on one run do not skew the mean.
    """

    total_cost_usd: float | None = None
    avg_cost_usd: float | None = None
    """Arithmetic mean over **evaluation rows** with non-null ``cost_usd`` (not grouped by run)."""

    evaluation_rows_with_cost: int = 0
    evaluation_rows_cost_not_available: int = 0

    avg_cost_usd_per_llm_run: float | None = None
    """``AVG`` of per-run ``SUM(cost_usd)`` for **LLM-bucket** rows with non-null cost; ``None`` if no such runs."""

    llm_runs_with_measured_cost: int = 0
    """Distinct ``run_id`` count in the population for ``avg_cost_usd_per_llm_run``."""

    avg_cost_usd_per_full_rag_run: float | None = None
    """Same as ``avg_cost_usd_per_llm_run`` but only runs that have ``generation_results``."""

    full_rag_runs_with_measured_cost: int = 0
    """Distinct ``run_id`` count for ``avg_cost_usd_per_full_rag_run``."""


class DashboardLlmReductionWorkloadRow(BaseModel):
    matched_workload_id: str
    dataset_id: int | None = None
    llm_only_runs: int
    hybrid_runs: int
    avg_llm_judge_calls_llm_only: float
    avg_llm_judge_calls_hybrid: float
    llm_judge_reduction_pct: float


class DashboardLlmReductionEvidence(BaseModel):
    matched_workloads: list[DashboardLlmReductionWorkloadRow] = Field(default_factory=list)
    workload_count: int = 0
    median_llm_judge_reduction_pct_across_workloads: float | None = None
    evidence_tier: Literal["sparse", "directional", "normal"] = "sparse"
    evidence_tier_note: str = ""
    validity_note: str = ""


class DashboardDiagnosisTimingEvidence(BaseModel):
    sessions_count: int = 0
    manual_completed_sessions: int = 0
    assisted_completed_sessions: int = 0
    median_diagnosis_duration_sec_manual: float | None = None
    median_diagnosis_duration_sec_assisted: float | None = None
    median_time_to_first_insight_sec_manual: float | None = None
    median_time_to_first_insight_sec_assisted: float | None = None
    median_delta_sec_assisted_vs_manual: float | None = None
    percent_reduction_vs_manual: float | None = None
    evidence_tier: Literal["insufficient", "limited", "normal"] = "insufficient"
    evidence_tier_note: str | None = None
    framework_note: str = ""


class DashboardRecentRun(BaseModel):
    run_id: int
    status: str
    created_at: datetime
    evaluator_type: Literal["heuristic", "llm", "none"]
    total_latency_ms: int | None = None
    cost_usd: float | None = None
    failure_type: str | None = None


class DashboardSummaryResponse(BaseModel):
    total_runs: int
    repeated_sampling_note: str = Field(
        description="Plain-language reminder that run count can exceed unique query cases (repeated sampling).",
    )
    scale: DashboardScaleMetrics
    status_counts: DashboardStatusCounts
    evaluator_counts: DashboardEvaluatorCounts
    latency: DashboardLatencySummary
    cost: DashboardCostSummary
    failure_type_counts: dict[str, int] = Field(default_factory=dict)
    """Counts per persisted ``failure_type`` (includes ``NO_FAILURE`` when present)."""

    model_failures: int = 0
    """Evaluation rows on **organic** runs where ``failure_type`` is set and not ``NO_FAILURE`` (quality / retrieval labels)."""

    recent_runs: list[DashboardRecentRun]
    diagnosis_timing: DashboardDiagnosisTimingEvidence = Field(
        default_factory=DashboardDiagnosisTimingEvidence
    )
    llm_reduction: DashboardLlmReductionEvidence = Field(default_factory=DashboardLlmReductionEvidence)
