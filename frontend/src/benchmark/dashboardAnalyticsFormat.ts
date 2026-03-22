/** Formatting helpers for dashboard analytics panels (testable, no React). */

import type { ConfigInsight, LatencyDistribution, TimeSeriesDay } from '../api/types'

export function formatScore(v: number | null | undefined): string {
  if (v == null) return 'N/A'
  return v.toFixed(3)
}

export function formatPercent(v: number | null | undefined): string {
  if (v == null) return 'N/A'
  return `${v.toFixed(1)}%`
}

export function formatDate(iso: string): string {
  // Expect YYYY-MM-DD from time_series
  return iso
}

/** Format a latency distribution row for display. */
export function formatDistRow(d: LatencyDistribution): {
  count: number
  min: string
  max: string
  avg: string
  median: string
  p95: string
} {
  const fmt = (v: number | null) => (v != null ? `${Math.round(v)} ms` : 'N/A')
  return {
    count: d.count,
    min: fmt(d.min_ms),
    max: fmt(d.max_ms),
    avg: fmt(d.avg_ms),
    median: fmt(d.median_ms),
    p95: fmt(d.p95_ms),
  }
}

/** Compute the max runs value in a time series for bar scaling. */
export function timeSeriesMaxRuns(days: TimeSeriesDay[]): number {
  if (days.length === 0) return 0
  return Math.max(...days.map((d) => d.runs))
}

/** Segments for a stacked “runs per day” bar (completed / failed / other). Counts in table remain API truth; bar clamps overlap. */
export type TimeSeriesStackSegment = {
  key: 'completed' | 'failed' | 'other'
  count: number
  /** Width % of the full bar (sums to ~100 for runs > 0). */
  pctOfRuns: number
}

export function timeSeriesDayStack(day: TimeSeriesDay): TimeSeriesStackSegment[] {
  const runs = day.runs
  if (runs <= 0) return []
  const completedSeg = Math.min(Math.max(0, day.completed), runs)
  const failedSeg = Math.min(Math.max(0, day.failed), runs - completedSeg)
  const other = runs - completedSeg - failedSeg
  return [
    { key: 'completed', count: completedSeg, pctOfRuns: (completedSeg / runs) * 100 },
    { key: 'failed', count: failedSeg, pctOfRuns: (failedSeg / runs) * 100 },
    { key: 'other', count: other, pctOfRuns: (other / runs) * 100 },
  ]
}

/** Scale for horizontal latency bars within one phase: max(median, p95, max_ms). */
export function latencyPhaseScaleMs(dist: LatencyDistribution): number {
  const vals = [dist.median_ms, dist.p95_ms, dist.max_ms].filter(
    (v): v is number => v != null && Number.isFinite(v) && v >= 0,
  )
  return vals.length > 0 ? Math.max(...vals, 1) : 1
}

/** Bar width 0–100 for value vs scale (single-phase comparison). */
export function barWidthPct(value: number | null | undefined, scaleMax: number): number {
  if (value == null || !Number.isFinite(value) || value < 0 || scaleMax <= 0) return 0
  return Math.min(100, (value / scaleMax) * 100)
}

export type FailureBarRow = { failureType: string; count: number; barPct: number }

/** Relative bar widths for top failure types (count / total). */
export function failureTypeBarPercents(
  sortedCounts: [string, number][],
  totalCount: number,
): FailureBarRow[] {
  if (totalCount <= 0) return []
  return sortedCounts.map(([failureType, count]) => ({
    failureType,
    count,
    barPct: (count / totalCount) * 100,
  }))
}

/** Sort failure counts descending by count. */
export function sortedFailureCounts(counts: Record<string, number>): [string, number][] {
  return Object.entries(counts).sort((a, b) => b[1] - a[1])
}

/** Dashboard table: most active configs first (stable tie-break by id). */
export function sortConfigInsightsByTracedDesc(rows: ConfigInsight[]): ConfigInsight[] {
  return [...rows].sort(
    (a, b) => b.traced_runs - a.traced_runs || a.pipeline_config_id - b.pipeline_config_id,
  )
}

/** ISO timestamp from API → locale string; null-safe. */
export function formatInsightTimestamp(iso: string | null | undefined): string {
  if (iso == null || iso === '') return 'N/A'
  try {
    return new Date(iso).toLocaleString()
  } catch {
    return iso
  }
}

/** Winners for insight badges + row highlight (fastest / highest relevance). */
export interface ConfigInsightBadgeWinners {
  fastestConfigId: number | null
  mostUsedConfigId: number | null
  highestRelevanceConfigId: number | null
  mostFailureProneConfigId: number | null
  cheapestConfigId: number | null
  /** Show “cheapest” badge when at least one config has a non-null avg cost. */
  showCheapestBadge: boolean
}

export function computeConfigInsightBadgeWinners(rows: ConfigInsight[]): ConfigInsightBadgeWinners {
  const empty: ConfigInsightBadgeWinners = {
    fastestConfigId: null,
    mostUsedConfigId: null,
    highestRelevanceConfigId: null,
    mostFailureProneConfigId: null,
    cheapestConfigId: null,
    showCheapestBadge: false,
  }
  if (rows.length === 0) return empty

  const showCheapestBadge = rows.some((r) => r.avg_cost_usd != null)

  const withLatency = rows.filter((r) => r.avg_total_latency_ms != null)
  const fastest =
    withLatency.length === 0
      ? null
      : [...withLatency].sort(
          (a, b) =>
            Number(a.avg_total_latency_ms) - Number(b.avg_total_latency_ms) ||
            a.pipeline_config_id - b.pipeline_config_id,
        )[0]

  const mostUsed = [...rows].sort(
    (a, b) => b.traced_runs - a.traced_runs || a.pipeline_config_id - b.pipeline_config_id,
  )[0]

  const withRel = rows.filter((r) => r.avg_retrieval_relevance != null)
  const highestRel =
    withRel.length === 0
      ? null
      : [...withRel].sort(
          (a, b) =>
            Number(b.avg_retrieval_relevance) - Number(a.avg_retrieval_relevance) ||
            a.pipeline_config_id - b.pipeline_config_id,
        )[0]

  const failProne = [...rows].sort((a, b) => {
    if (b.failed_runs !== a.failed_runs) return b.failed_runs - a.failed_runs
    const ra = a.traced_runs > 0 ? a.failed_runs / a.traced_runs : 0
    const rb = b.traced_runs > 0 ? b.failed_runs / b.traced_runs : 0
    if (rb !== ra) return rb - ra
    return a.pipeline_config_id - b.pipeline_config_id
  })[0]
  const mostFailureProne = failProne.failed_runs > 0 ? failProne : null

  const withAvgCost = rows.filter((r) => r.avg_cost_usd != null)
  const cheapest =
    withAvgCost.length === 0
      ? null
      : [...withAvgCost].sort(
          (a, b) =>
            Number(a.avg_cost_usd) - Number(b.avg_cost_usd) ||
            a.pipeline_config_id - b.pipeline_config_id,
        )[0]

  return {
    fastestConfigId: fastest?.pipeline_config_id ?? null,
    mostUsedConfigId: mostUsed.pipeline_config_id,
    highestRelevanceConfigId: highestRel?.pipeline_config_id ?? null,
    mostFailureProneConfigId: mostFailureProne?.pipeline_config_id ?? null,
    cheapestConfigId: cheapest?.pipeline_config_id ?? null,
    showCheapestBadge,
  }
}

/** Row highlight: lowest latency or highest relevance winner (can be two different configs). */
export function configInsightRowIsHighlighted(
  configId: number,
  winners: ConfigInsightBadgeWinners,
): boolean {
  return (
    (winners.fastestConfigId != null && configId === winners.fastestConfigId) ||
    (winners.highestRelevanceConfigId != null && configId === winners.highestRelevanceConfigId)
  )
}

/** Table row classes: quality winners + failure-prone standout. */
export function configInsightRowClasses(
  configId: number,
  winners: ConfigInsightBadgeWinners,
): string | undefined {
  const parts: string[] = []
  if (configInsightRowIsHighlighted(configId, winners)) {
    parts.push('cl-config-insight-row--highlight')
  }
  if (
    winners.mostFailureProneConfigId != null &&
    configId === winners.mostFailureProneConfigId
  ) {
    parts.push('cl-config-insight-row--attention')
  }
  return parts.length > 0 ? parts.join(' ') : undefined
}
