import type { ConfigComparisonResponse, ConfigScoreComparisonSummary } from '../api/types'

/** All-null summary — matches backend when no comparable configs / scores. */
export function nullScoreSummary(): ConfigScoreComparisonSummary {
  return {
    best_config_faithfulness: null,
    worst_config_faithfulness: null,
    faithfulness_delta_pct: null,
    best_config_completeness: null,
    worst_config_completeness: null,
    completeness_delta_pct: null,
  }
}

/** Minimal `evaluator_type: both` payload for Vitest mocks and defaults. */
export function emptyConfigComparisonBoth(
  over: Partial<ConfigComparisonResponse> = {},
): ConfigComparisonResponse {
  return {
    evaluator_type: 'both',
    pipeline_config_ids: [],
    configs: null,
    buckets: { heuristic: [], llm: [] },
    score_comparison: null,
    score_comparison_buckets: {
      heuristic: nullScoreSummary(),
      llm: nullScoreSummary(),
    },
    comparison_confidence: 'LOW',
    comparison_statistically_reliable: false,
    min_traced_runs_across_configs: 0,
    recommended_min_traced_runs_for_valid_comparison: 20,
    unique_queries_compared: 0,
    effective_sample_size: 0,
    recommended_min_unique_queries_for_valid_comparison: 10,
    ...over,
  }
}
