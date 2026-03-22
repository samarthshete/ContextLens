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
    """Runs with ≥1 ``retrieval_results`` row and ≥1 ``evaluation_results`` row (same as metrics aggregate)."""
    configs_tested: int = 0
    """``COUNT(DISTINCT runs.pipeline_config_id)`` over all run rows (same as metrics aggregate)."""
    documents_processed: int = 0
    """Documents with ``status == 'processed'`` (successful ingest per upload pipeline)."""
    chunks_indexed: int = 0
    """Rows in ``chunks`` (stored chunk records; cascade with documents)."""


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

    ``avg_total_latency_ms`` and ``end_to_end_run_latency_*_sec`` use the same non-null
    ``runs.total_latency_ms`` population (mean + ``percentile_cont(0.95)``); seconds are
    milliseconds / 1000. ``None`` = insufficient data (no samples).
    """

    avg_retrieval_latency_ms: float | None = None
    retrieval_latency_p50_ms: float | None = None
    retrieval_latency_p95_ms: float | None = None
    avg_generation_latency_ms: float | None = None
    avg_evaluation_latency_ms: float | None = None
    avg_total_latency_ms: float | None = None
    end_to_end_run_latency_avg_sec: float | None = None
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
    scale: DashboardScaleMetrics
    status_counts: DashboardStatusCounts
    evaluator_counts: DashboardEvaluatorCounts
    latency: DashboardLatencySummary
    cost: DashboardCostSummary
    failure_type_counts: dict[str, int] = Field(default_factory=dict)
    recent_runs: list[DashboardRecentRun]
