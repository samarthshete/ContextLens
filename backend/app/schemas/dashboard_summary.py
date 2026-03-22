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


class DashboardEvaluatorCounts(BaseModel):
    """Distinct runs with an evaluation row in each bucket (see ``evaluator_bucket``)."""

    heuristic_runs: int = 0
    llm_runs: int = 0
    runs_without_evaluation: int = 0


class DashboardLatencySummary(BaseModel):
    """AVG over ``runs`` where each latency column IS NOT NULL. ``None`` = no samples."""

    avg_retrieval_latency_ms: float | None = None
    avg_generation_latency_ms: float | None = None
    avg_evaluation_latency_ms: float | None = None
    avg_total_latency_ms: float | None = None


class DashboardCostSummary(BaseModel):
    """From ``evaluation_results.cost_usd`` only — aligns with trace cost semantics (NULL = N/A)."""

    total_cost_usd: float | None = None
    avg_cost_usd: float | None = None
    evaluation_rows_with_cost: int = 0
    evaluation_rows_cost_not_available: int = 0


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
    status_counts: DashboardStatusCounts
    evaluator_counts: DashboardEvaluatorCounts
    latency: DashboardLatencySummary
    cost: DashboardCostSummary
    failure_type_counts: dict[str, int] = Field(default_factory=dict)
    recent_runs: list[DashboardRecentRun]
