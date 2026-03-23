"""Pipeline config comparison from stored runs."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ComparisonConfidence = Literal["LOW", "MEDIUM", "HIGH"]


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
    stddev_samp_completeness: float | None = Field(
        default=None,
        description="Sample stddev of completeness in bucket; null if not measurable (e.g. n<2).",
    )
    stddev_samp_faithfulness: float | None = Field(
        default=None,
        description="Sample stddev of faithfulness in bucket; null if not measurable (e.g. n<2).",
    )
    stddev_samp_retrieval_relevance: float | None = Field(
        default=None,
        description="Sample stddev of retrieval_relevance in bucket; null if not measurable (e.g. n<2).",
    )
    stddev_samp_context_coverage: float | None = Field(
        default=None,
        description="Sample stddev of context_coverage in bucket; null if not measurable (e.g. n<2).",
    )
    stddev_samp_retrieval_latency_ms: float | None = Field(
        default=None,
        description="Sample stddev of runs.retrieval_latency_ms in bucket; null if n<2.",
    )
    stddev_samp_total_latency_ms: float | None = Field(
        default=None,
        description="Sample stddev of runs.total_latency_ms in bucket; null if n<2.",
    )


class ConfigScoreComparisonSummary(BaseModel):
    """Cross-config extremes within one evaluator bucket for the requested config ids.

    Use ``include_faithfulness=False`` only when that dimension is not meaningful for the bucket.

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

    evaluator_type: Literal["heuristic", "llm", "both"]
    pipeline_config_ids: list[int]
    configs: list[ConfigComparisonMetrics] | None = None
    buckets: dict[str, list[ConfigComparisonMetrics]] | None = None
    score_comparison: ConfigScoreComparisonSummary | None = Field(
        default=None,
        description="Set for single-bucket responses (llm or heuristic).",
    )
    score_comparison_buckets: dict[str, ConfigScoreComparisonSummary] | None = Field(
        default=None,
        description="Set when evaluator_type is both — keys heuristic, llm.",
    )
    dataset_id: int | None = Field(
        default=None,
        description="When set, only runs whose query_case belongs to this dataset are included.",
    )
    strict_comparison_applied: bool = Field(
        default=False,
        description="True when strict_comparison was requested and integrity rules were enforced.",
    )
    min_traced_runs_enforced: int | None = Field(
        default=None,
        description="Minimum traced runs per config that was enforced (null if none).",
    )
    comparison_confidence: ComparisonConfidence = Field(
        description="Heuristic tier from min traced_runs across configs in this response (LOW/MEDIUM/HIGH).",
    )
    comparison_statistically_reliable: bool = Field(
        description="True when min traced_runs across configs >= recommended threshold (default 20).",
    )
    min_traced_runs_across_configs: int = Field(ge=0)
    recommended_min_traced_runs_for_valid_comparison: int = Field(
        default=20,
        ge=1,
        description="Documented minimum runs per config for high-confidence comparisons.",
    )
