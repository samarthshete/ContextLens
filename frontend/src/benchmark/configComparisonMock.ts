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
    ...over,
  }
}
