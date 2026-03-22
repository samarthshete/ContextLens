/**
 * Load merged run rows for the queue browser using existing GET /runs filters (no new API).
 */

import type { ListRunsParams, RunListItem, RunListResponse } from '../api/types'

/** Status slices fetched in parallel; dedupe by run_id; sort newest first. */
export const QUEUE_BROWSER_STATUS_SLICES = [
  'pending',
  'running',
  'retrieval_completed',
  'generation_completed',
  'failed',
] as const

export type QueueBrowserListFn = (params: ListRunsParams) => Promise<RunListResponse>

const SLICE_LIMIT = 20
/** Cap merged rows so the table + optional queue-status refreshes stay bounded. */
export const QUEUE_BROWSER_MAX_ROWS = 45

export async function loadQueueBrowserRunRows(
  listRuns: QueueBrowserListFn,
): Promise<{ items: RunListItem[]; sliceErrors: string[] }> {
  const sliceErrors: string[] = []
  const map = new Map<number, RunListItem>()

  const settled = await Promise.allSettled(
    QUEUE_BROWSER_STATUS_SLICES.map((status) =>
      listRuns({ limit: SLICE_LIMIT, offset: 0, status }),
    ),
  )

  settled.forEach((r, i) => {
    const status = QUEUE_BROWSER_STATUS_SLICES[i]
    if (r.status === 'fulfilled') {
      for (const it of r.value.items) map.set(it.run_id, it)
    } else {
      const msg = r.reason instanceof Error ? r.reason.message : String(r.reason)
      sliceErrors.push(`${status}: ${msg}`)
    }
  })

  const items = [...map.values()]
    .sort((a, b) => {
      const c = b.created_at.localeCompare(a.created_at)
      if (c !== 0) return c
      return b.run_id - a.run_id
    })
    .slice(0, QUEUE_BROWSER_MAX_ROWS)

  return { items, sliceErrors }
}
