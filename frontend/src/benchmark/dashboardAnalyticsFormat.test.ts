import { describe, expect, it } from 'vitest'
import type { ConfigInsight, LatencyDistribution, TimeSeriesDay } from '../api/types'
import {
  barWidthPct,
  computeConfigInsightBadgeWinners,
  computeTopKSpeedRelevanceTradeoffNote,
  configInsightRowClasses,
  configInsightRowIsHighlighted,
  failureTypeBarPercents,
  formatDistRow,
  formatInsightTimestamp,
  inferTopKFromConfigName,
  formatPercent,
  formatScore,
  latencyPhaseScaleMs,
  sortConfigInsightsByTracedDesc,
  sortedFailureCounts,
  timeSeriesDayStack,
  timeSeriesMaxRuns,
} from './dashboardAnalyticsFormat'

function insight(partial: Partial<ConfigInsight> & Pick<ConfigInsight, 'pipeline_config_id' | 'pipeline_config_name'>): ConfigInsight {
  return {
    traced_runs: 0,
    completed_runs: 0,
    failed_runs: 0,
    avg_total_latency_ms: null,
    min_total_latency_ms: null,
    max_total_latency_ms: null,
    avg_cost_usd: null,
    total_cost_usd: null,
    avg_retrieval_relevance: null,
    avg_context_coverage: null,
    avg_completeness: null,
    avg_faithfulness: null,
    latest_run_at: null,
    top_failure_type: null,
    ...partial,
  }
}

describe('dashboardAnalyticsFormat', () => {
  describe('formatScore', () => {
    it('formats number to 3 decimals', () => {
      expect(formatScore(0.123456)).toBe('0.123')
    })
    it('returns N/A for null', () => {
      expect(formatScore(null)).toBe('N/A')
    })
    it('returns N/A for undefined', () => {
      expect(formatScore(undefined)).toBe('N/A')
    })
  })

  describe('formatPercent', () => {
    it('formats to one decimal with %', () => {
      expect(formatPercent(42.567)).toBe('42.6%')
    })
    it('returns N/A for null', () => {
      expect(formatPercent(null)).toBe('N/A')
    })
  })

  describe('formatDistRow', () => {
    it('formats a full distribution row', () => {
      const d: LatencyDistribution = {
        count: 10,
        min_ms: 5,
        max_ms: 200,
        avg_ms: 50.5,
        median_ms: 40,
        p95_ms: 180,
      }
      const row = formatDistRow(d)
      expect(row.count).toBe(10)
      expect(row.min).toBe('5 ms')
      expect(row.max).toBe('200 ms')
      expect(row.avg).toBe('51 ms')
      expect(row.median).toBe('40 ms')
      expect(row.p95).toBe('180 ms')
    })

    it('shows N/A for null values', () => {
      const d: LatencyDistribution = {
        count: 0,
        min_ms: null,
        max_ms: null,
        avg_ms: null,
        median_ms: null,
        p95_ms: null,
      }
      const row = formatDistRow(d)
      expect(row.min).toBe('N/A')
      expect(row.median).toBe('N/A')
    })
  })

  describe('timeSeriesMaxRuns', () => {
    it('returns max runs from days', () => {
      const days: TimeSeriesDay[] = [
        { date: '2026-01-01', runs: 3, completed: 3, failed: 0, avg_total_latency_ms: null, avg_cost_usd: null, failure_count: 0 },
        { date: '2026-01-02', runs: 7, completed: 5, failed: 2, avg_total_latency_ms: null, avg_cost_usd: null, failure_count: 1 },
      ]
      expect(timeSeriesMaxRuns(days)).toBe(7)
    })

    it('returns 0 for empty array', () => {
      expect(timeSeriesMaxRuns([])).toBe(0)
    })
  })

  describe('sortedFailureCounts', () => {
    it('sorts descending by count', () => {
      const result = sortedFailureCounts({ UNKNOWN: 2, RETRIEVAL_MISS: 5, MIXED: 1 })
      expect(result).toEqual([
        ['RETRIEVAL_MISS', 5],
        ['UNKNOWN', 2],
        ['MIXED', 1],
      ])
    })

    it('returns empty for empty input', () => {
      expect(sortedFailureCounts({})).toEqual([])
    })
  })

  describe('sortConfigInsightsByTracedDesc', () => {
    it('sorts by traced_runs descending, then id ascending', () => {
      const rows = [
        insight({ pipeline_config_id: 2, pipeline_config_name: 'B', traced_runs: 3 }),
        insight({ pipeline_config_id: 1, pipeline_config_name: 'A', traced_runs: 10 }),
        insight({ pipeline_config_id: 3, pipeline_config_name: 'C', traced_runs: 10 }),
      ]
      const sorted = sortConfigInsightsByTracedDesc(rows).map((r) => r.pipeline_config_id)
      expect(sorted).toEqual([1, 3, 2])
    })
  })

  describe('formatInsightTimestamp', () => {
    it('returns N/A for null', () => {
      expect(formatInsightTimestamp(null)).toBe('N/A')
    })
    it('returns a non-empty string for valid ISO', () => {
      const s = formatInsightTimestamp('2026-01-15T12:00:00.000Z')
      expect(s.length).toBeGreaterThan(4)
    })
  })

  describe('computeConfigInsightBadgeWinners', () => {
    it('returns null winners for empty list', () => {
      const w = computeConfigInsightBadgeWinners([])
      expect(w.fastestConfigId).toBeNull()
      expect(w.showCheapestBadge).toBe(false)
    })

    it('picks fastest, most used, highest relevance, failure-prone, cheapest', () => {
      const rows = [
        insight({
          pipeline_config_id: 1,
          pipeline_config_name: 'Alpha',
          traced_runs: 10,
          failed_runs: 2,
          avg_total_latency_ms: 200,
          avg_retrieval_relevance: 0.5,
          avg_cost_usd: 0.02,
        }),
        insight({
          pipeline_config_id: 2,
          pipeline_config_name: 'Beta',
          traced_runs: 5,
          failed_runs: 0,
          avg_total_latency_ms: 80,
          avg_retrieval_relevance: 0.95,
          avg_cost_usd: 0.01,
        }),
      ]
      const w = computeConfigInsightBadgeWinners(rows)
      expect(w.mostUsedConfigId).toBe(1)
      expect(w.fastestConfigId).toBe(2)
      expect(w.highestRelevanceConfigId).toBe(2)
      expect(w.mostFailureProneConfigId).toBe(1)
      expect(w.cheapestConfigId).toBe(2)
      expect(w.showCheapestBadge).toBe(true)
    })

    it('omits most failure-prone when no failures', () => {
      const rows = [
        insight({ pipeline_config_id: 1, pipeline_config_name: 'A', traced_runs: 2, failed_runs: 0 }),
        insight({ pipeline_config_id: 2, pipeline_config_name: 'B', traced_runs: 1, failed_runs: 0 }),
      ]
      const w = computeConfigInsightBadgeWinners(rows)
      expect(w.mostFailureProneConfigId).toBeNull()
    })
  })

  describe('configInsightRowIsHighlighted', () => {
    it('true for fastest or highest-relevance id', () => {
      const w = {
        fastestConfigId: 2,
        mostUsedConfigId: 1,
        highestRelevanceConfigId: 3,
        mostFailureProneConfigId: null,
        cheapestConfigId: null,
        showCheapestBadge: false,
      }
      expect(configInsightRowIsHighlighted(2, w)).toBe(true)
      expect(configInsightRowIsHighlighted(3, w)).toBe(true)
      expect(configInsightRowIsHighlighted(1, w)).toBe(false)
    })
  })

  describe('timeSeriesDayStack', () => {
    it('splits runs into completed, failed, other without exceeding runs', () => {
      const segs = timeSeriesDayStack({
        date: 'd',
        runs: 10,
        completed: 6,
        failed: 2,
        avg_total_latency_ms: null,
        avg_cost_usd: null,
        failure_count: 0,
      })
      expect(segs.map((s) => s.count)).toEqual([6, 2, 2])
      expect(segs.reduce((a, s) => a + s.pctOfRuns, 0)).toBeCloseTo(100, 5)
    })

    it('returns empty when runs is 0', () => {
      expect(
        timeSeriesDayStack({
          date: 'd',
          runs: 0,
          completed: 3,
          failed: 1,
          avg_total_latency_ms: null,
          avg_cost_usd: null,
          failure_count: 0,
        }),
      ).toEqual([])
    })
  })

  describe('latencyPhaseScaleMs & barWidthPct', () => {
    it('scale is max of present metrics', () => {
      const d: LatencyDistribution = {
        count: 5,
        min_ms: 1,
        max_ms: 300,
        avg_ms: 50,
        median_ms: 40,
        p95_ms: 200,
      }
      expect(latencyPhaseScaleMs(d)).toBe(300)
      expect(barWidthPct(150, 300)).toBe(50)
    })

    it('barWidthPct is 0 for null', () => {
      expect(barWidthPct(null, 100)).toBe(0)
    })
  })

  describe('failureTypeBarPercents', () => {
    it('computes widths from total', () => {
      const sorted: [string, number][] = [
        ['A', 3],
        ['B', 1],
      ]
      const rows = failureTypeBarPercents(sorted, 4)
      expect(rows[0].barPct).toBe(75)
      expect(rows[1].barPct).toBe(25)
    })
  })

  describe('inferTopKFromConfigName', () => {
    it('parses common benchmark name patterns', () => {
      expect(inferTopKFromConfigName('stress_topk8')).toBe(8)
      expect(inferTopKFromConfigName('evidence_topk3')).toBe(3)
      expect(inferTopKFromConfigName('no match here')).toBeNull()
    })
  })

  describe('computeTopKSpeedRelevanceTradeoffNote', () => {
    it('returns tradeoff when higher top_k is faster with worse relevance', () => {
      const rows: ConfigInsight[] = [
        insight({
          pipeline_config_id: 1,
          pipeline_config_name: 'stress_topk3',
          traced_runs: 5,
          avg_total_latency_ms: 200,
          avg_retrieval_relevance: 0.7,
        }),
        insight({
          pipeline_config_id: 2,
          pipeline_config_name: 'stress_topk8',
          traced_runs: 5,
          avg_total_latency_ms: 120,
          avg_retrieval_relevance: 0.45,
        }),
      ]
      const note = computeTopKSpeedRelevanceTradeoffNote(rows)
      expect(note).toContain('Tradeoff')
      expect(note).toContain('top_k')
    })

    it('returns null when latency or relevance do not match pattern', () => {
      const rows: ConfigInsight[] = [
        insight({
          pipeline_config_id: 1,
          pipeline_config_name: 'stress_topk3',
          traced_runs: 5,
          avg_total_latency_ms: 100,
          avg_retrieval_relevance: 0.5,
        }),
        insight({
          pipeline_config_id: 2,
          pipeline_config_name: 'stress_topk8',
          traced_runs: 5,
          avg_total_latency_ms: 200,
          avg_retrieval_relevance: 0.6,
        }),
      ]
      expect(computeTopKSpeedRelevanceTradeoffNote(rows)).toBeNull()
    })
  })

  describe('configInsightRowClasses', () => {
    it('combines highlight and attention on different rows', () => {
      const w = {
        fastestConfigId: 2,
        mostUsedConfigId: 1,
        highestRelevanceConfigId: 2,
        mostFailureProneConfigId: 1,
        cheapestConfigId: null,
        showCheapestBadge: false,
      }
      expect(configInsightRowClasses(2, w)).toMatch(/highlight/)
      expect(configInsightRowClasses(2, w)).not.toMatch(/attention/)
      expect(configInsightRowClasses(1, w)).toMatch(/attention/)
      expect(configInsightRowClasses(1, w)).not.toMatch(/highlight/)
    })
  })
})
