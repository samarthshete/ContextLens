import type { Dataset } from '../api/types'

/** Default dashboard selection: newest registry row by `created_at`. */
export function pickLatestDatasetId(datasets: Dataset[]): number | null {
  if (datasets.length === 0) return null
  const sorted = [...datasets].sort((a, b) => b.created_at.localeCompare(a.created_at))
  return sorted[0]!.id
}
