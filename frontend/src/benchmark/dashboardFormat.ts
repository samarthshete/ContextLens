/** Formatting helpers for dashboard metrics (testable, no React). */

export function formatLatencyMs(v: number | null | undefined): string {
  if (v == null || Number.isNaN(Number(v))) return 'N/A'
  return `${Math.round(Number(v))} ms`
}

/** USD from API; ``null``/undefined → not available; real zero shown explicitly. */
export function formatUsd(v: number | null | undefined): string {
  if (v == null) return 'N/A'
  const n = Number(v)
  if (Number.isNaN(n)) return 'N/A'
  if (n === 0) return '$0.00'
  return `$${n.toFixed(6)}`
}

export function costAvailabilityLine(cost: {
  evaluation_rows_with_cost: number
  evaluation_rows_cost_not_available: number
}): string {
  const { evaluation_rows_with_cost: w, evaluation_rows_cost_not_available: na } = cost
  if (w === 0 && na === 0) return 'No evaluation rows yet.'
  return `${w} row(s) with cost · ${na} row(s) cost N/A (null)`
}
