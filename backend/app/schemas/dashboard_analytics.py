"""Response for ``GET /api/v1/runs/dashboard-analytics`` — richer analytics layer."""

from __future__ import annotations

from pydantic import BaseModel, Field


class TimeSeriesDay(BaseModel):
    """Aggregates for a single calendar day."""

    date: str
    """ISO date string (YYYY-MM-DD)."""
    runs: int = 0
    completed: int = 0
    failed: int = 0
    avg_total_latency_ms: float | None = None
    avg_cost_usd: float | None = None
    failure_count: int = 0


class LatencyDistribution(BaseModel):
    """Min/max/avg/median/p95/count for a single latency phase."""

    count: int = 0
    min_ms: float | None = None
    max_ms: float | None = None
    avg_ms: float | None = None
    median_ms: float | None = None
    p95_ms: float | None = None


class LatencyDistributionSection(BaseModel):
    """Distribution stats for each latency phase."""

    retrieval: LatencyDistribution = Field(default_factory=LatencyDistribution)
    generation: LatencyDistribution = Field(default_factory=LatencyDistribution)
    evaluation: LatencyDistribution = Field(default_factory=LatencyDistribution)
    total: LatencyDistribution = Field(default_factory=LatencyDistribution)


class FailureByConfig(BaseModel):
    """Failure counts for a single pipeline config."""

    pipeline_config_id: int
    pipeline_config_name: str
    failure_counts: dict[str, int] = Field(default_factory=dict)
    total_failures: int = 0


class RecentFailedRun(BaseModel):
    """Minimal info for a recently failed run."""

    run_id: int
    status: str
    created_at: str
    failure_type: str | None = None
    pipeline_config_id: int


class FailureAnalysisSection(BaseModel):
    """Overall + per-config failure breakdown."""

    overall_counts: dict[str, int] = Field(default_factory=dict)
    overall_percentages: dict[str, float] = Field(default_factory=dict)
    by_config: list[FailureByConfig] = Field(default_factory=list)
    recent_failed_runs: list[RecentFailedRun] = Field(default_factory=list)


class ConfigInsight(BaseModel):
    """Per-config aggregate metrics."""

    pipeline_config_id: int
    pipeline_config_name: str
    traced_runs: int = 0
    completed_runs: int = 0
    failed_runs: int = 0
    avg_total_latency_ms: float | None = None
    min_total_latency_ms: float | None = None
    max_total_latency_ms: float | None = None
    avg_cost_usd: float | None = None
    total_cost_usd: float | None = None
    avg_retrieval_relevance: float | None = None
    avg_context_coverage: float | None = None
    avg_completeness: float | None = None
    avg_faithfulness: float | None = None
    latest_run_at: str | None = None
    top_failure_type: str | None = None


class DashboardAnalyticsResponse(BaseModel):
    """Full analytics payload for the dashboard."""

    time_series: list[TimeSeriesDay] = Field(default_factory=list)
    latency_distribution: LatencyDistributionSection = Field(
        default_factory=LatencyDistributionSection
    )
    failure_analysis: FailureAnalysisSection = Field(default_factory=FailureAnalysisSection)
    config_insights: list[ConfigInsight] = Field(default_factory=list)
