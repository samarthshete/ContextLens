export function formatScoreDeltaPct(v: number | null | undefined): string {
  if (v == null || Number.isNaN(Number(v))) return 'N/A'
  return `${Number(v).toFixed(1)}%`
}
