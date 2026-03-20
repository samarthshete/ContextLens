"""Pipeline config comparison from stored runs."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ConfigComparisonMetrics(BaseModel):
    pipeline_config_id: int
    traced_runs: int = Field(ge=0)
    avg_retrieval_latency_ms: float | None = None
    p95_retrieval_latency_ms: float | None = None
    avg_evaluation_latency_ms: float | None = None
    p95_evaluation_latency_ms: float | None = None
    avg_total_latency_ms: float | None = None
    p95_total_latency_ms: float | None = None
    avg_groundedness: float | None = None
    avg_completeness: float | None = None
    avg_retrieval_relevance: float | None = None
    avg_context_coverage: float | None = None
    failure_type_counts: dict[str, int] = Field(default_factory=dict)
    avg_evaluation_cost_per_run_usd: float | None = None


class ConfigComparisonResponse(BaseModel):
    """When ``evaluator_type`` is ``both``, ``buckets`` is set. Otherwise ``configs``."""

    evaluator_type: Literal["heuristic", "llm", "both", "combined"]
    pipeline_config_ids: list[int]
    configs: list[ConfigComparisonMetrics] | None = None
    buckets: dict[str, list[ConfigComparisonMetrics]] | None = None
