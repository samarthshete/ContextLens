import { describe, expect, it } from 'vitest'
import type { ConfigComparisonMetrics, ConfigScoreComparisonSummary } from '../api/types'
import { completenessAbsSpreadFromMetrics, formatScoreDeltaPct } from './scoreComparisonFormat'

describe('formatScoreDeltaPct', () => {
  it('returns N/A for nullish or NaN', () => {
    expect(formatScoreDeltaPct(null)).toBe('N/A')
    expect(formatScoreDeltaPct(undefined)).toBe('N/A')
    expect(formatScoreDeltaPct(Number.NaN)).toBe('N/A')
  })

  it('formats finite numbers to one decimal and percent suffix', () => {
    expect(formatScoreDeltaPct(25.5)).toBe('25.5%')
    expect(formatScoreDeltaPct(0)).toBe('0.0%')
  })
})

describe('completenessAbsSpreadFromMetrics', () => {
  const row = (partial: Partial<ConfigComparisonMetrics> & Pick<ConfigComparisonMetrics, 'pipeline_config_id'>): ConfigComparisonMetrics => ({
    pipeline_config_id: partial.pipeline_config_id,
    traced_runs: partial.traced_runs ?? 1,
    avg_faithfulness: partial.avg_faithfulness ?? null,
    avg_retrieval_latency_ms: null,
    p95_retrieval_latency_ms: null,
    avg_evaluation_latency_ms: null,
    p95_evaluation_latency_ms: null,
    avg_total_latency_ms: null,
    p95_total_latency_ms: null,
    avg_groundedness: null,
    avg_completeness: partial.avg_completeness ?? null,
    avg_retrieval_relevance: null,
    avg_context_coverage: null,
    failure_type_counts: {},
    avg_evaluation_cost_per_run_usd: null,
  })

  it('returns absolute spread between best and worst config completeness averages', () => {
    const rows = [
      row({ pipeline_config_id: 1, avg_completeness: 0.5 }),
      row({ pipeline_config_id: 2, avg_completeness: 0.52 }),
    ]
    const summary: ConfigScoreComparisonSummary = {
      best_config_faithfulness: null,
      worst_config_faithfulness: null,
      faithfulness_delta_pct: null,
      best_config_completeness: 2,
      worst_config_completeness: 1,
      completeness_delta_pct: 4.0,
    }
    expect(completenessAbsSpreadFromMetrics(rows, summary)).toBeCloseTo(0.02, 6)
  })

  it('returns null when ids or averages are missing', () => {
    expect(
      completenessAbsSpreadFromMetrics([], {
        best_config_faithfulness: null,
        worst_config_faithfulness: null,
        faithfulness_delta_pct: null,
        best_config_completeness: 1,
        worst_config_completeness: 2,
        completeness_delta_pct: null,
      }),
    ).toBeNull()
  })
})
