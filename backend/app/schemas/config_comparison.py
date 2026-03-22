"""Pipeline config comparison from stored runs."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ConfigComparisonMetrics(BaseModel):
    pipeline_config_id: int
    traced_runs: int = Field(ge=0)
    avg_faithfulness: float | None = None
    """``AVG(evaluation_results.faithfulness)`` over traced runs in this bucket (non-null only)."""
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


class ConfigScoreComparisonSummary(BaseModel):
    """Cross-config extremes within one evaluator bucket for the requested config ids.

    **Faithfulness** is omitted (all null) when ``combine_evaluators`` merged heuristic + LLM rows,
    because that blend is not comparable. **Completeness** is still computed on the merged set.

    **Delta %** = ``100 * (best_avg - worst_avg) / worst_avg`` when ``worst_avg > 1e-9``; else
    ``null`` (no defensible relative baseline). **0.0** when best and worst averages are equal.
    Ties: **best** = highest score, then **lowest** ``pipeline_config_id``; **worst** = lowest score,
    then **lowest** ``pipeline_config_id``.
    """

    best_config_faithfulness: int | None = None
    worst_config_faithfulness: int | None = None
    faithfulness_delta_pct: float | None = None
    best_config_completeness: int | None = None
    worst_config_completeness: int | None = None
    completeness_delta_pct: float | None = None


class ConfigComparisonResponse(BaseModel):
    """When ``evaluator_type`` is ``both``, ``buckets`` is set. Otherwise ``configs``."""

    evaluator_type: Literal["heuristic", "llm", "both", "combined"]
    pipeline_config_ids: list[int]
    configs: list[ConfigComparisonMetrics] | None = None
    buckets: dict[str, list[ConfigComparisonMetrics]] | None = None
    score_comparison: ConfigScoreComparisonSummary | None = None
    """Set for single-bucket responses (``llm``, ``heuristic``, or ``combined``)."""
    score_comparison_buckets: dict[str, ConfigScoreComparisonSummary] | None = None
    """Set when ``evaluator_type`` is ``both`` — keys ``heuristic``, ``llm``."""
