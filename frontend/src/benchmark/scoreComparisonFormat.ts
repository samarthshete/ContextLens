import type { ConfigComparisonMetrics, ConfigScoreComparisonSummary } from '../api/types'

export function formatScoreDeltaPct(v: number | null | undefined): string {
  if (v == null || Number.isNaN(Number(v))) return 'N/A'
  return `${Number(v).toFixed(1)}%`
}

/** |avg_completeness(best) − avg_completeness(worst)| from per-config metrics; null if not derivable. */
export function completenessAbsSpreadFromMetrics(
  rows: ConfigComparisonMetrics[],
  summary: ConfigScoreComparisonSummary,
): number | null {
  const bid = summary.best_config_completeness
  const wid = summary.worst_config_completeness
  if (bid == null || wid == null) return null
  const b = rows.find((r) => r.pipeline_config_id === bid)?.avg_completeness
  const w = rows.find((r) => r.pipeline_config_id === wid)?.avg_completeness
  if (b == null || w == null) return null
  return Math.abs(b - w)
}
