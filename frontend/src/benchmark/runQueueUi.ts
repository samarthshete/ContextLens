import type { RunQueueStatusResponse } from '../api/types'

/** Whether the Requeue button should be offered (full pipeline + server says eligible). */
export function shouldShowRequeueButton(q: RunQueueStatusResponse): boolean {
  return q.pipeline === 'full' && q.requeue_eligible
}

export function formatQueueField(value: string | null | undefined): string {
  if (value == null || value === '') return '—'
  return value
}
