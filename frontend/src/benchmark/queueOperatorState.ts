import type { RunQueueStatusResponse } from '../api/types'

/**
 * Browser-side operator readout for queue / requeue — derived only from
 * `GET /runs/{id}/queue-status` fields (no invented server semantics).
 * @see backend `get_run_queue_status` — full runs: ineligible ⇒ lock or `detail` explains why.
 */

export type QueueRowRemoteState =
  | { phase: 'not_fetched' }
  | { phase: 'loading' }
  | { phase: 'error'; message: string }
  | { phase: 'ok'; q: RunQueueStatusResponse }

export function parseQueueRowRemoteState(qs: {
  loading: boolean
  data: RunQueueStatusResponse | null
  error: string | null
} | undefined): QueueRowRemoteState {
  if (qs == null) {
    return { phase: 'not_fetched' }
  }
  if (qs.loading) {
    return { phase: 'loading' }
  }
  if (qs.error) {
    return { phase: 'error', message: qs.error }
  }
  if (qs.data) {
    return { phase: 'ok', q: qs.data }
  }
  return { phase: 'not_fetched' }
}

/** Stable codes for styling and tests. */
export type OperatorQueueKind =
  | 'need_queue_status'
  | 'loading'
  | 'error'
  | 'heuristic_no_rq'
  | 'full_recovery_ready'
  | 'full_lock_blocks_requeue'
  | 'full_not_eligible'
  | 'full_ineligible_no_detail'

export type OperatorQueuePresentation = {
  kind: OperatorQueueKind
  badge: string
  description: string
}

function formatQueueField(value: string | null | undefined): string {
  if (value == null || value === '') {
    return '—'
  }
  return value
}

function normalizeRqStatus(raw: string | null | undefined): string | null {
  if (raw == null || raw === '') {
    return null
  }
  return raw.toLowerCase()
}

function recoveryReadySuffix(q: RunQueueStatusResponse): string {
  const st = normalizeRqStatus(q.rq_job_status)
  if (st === 'queued') {
    return ' (RQ: queued)'
  }
  if (st === 'started') {
    return ' (RQ: running)'
  }
  if (st === 'finished') {
    return ' (RQ: finished)'
  }
  if (st === 'failed' || st === 'stopped' || st === 'canceled' || st === 'cancelled') {
    return ' (RQ: terminal — failed/stopped)'
  }
  if (q.job_id && q.rq_job_status) {
    return ` (RQ: ${q.rq_job_status})`
  }
  return ' (RQ job not visible — registry scan miss or TTL)'
}

/**
 * Map a successful queue-status payload to operator-facing copy.
 * Preconditions: `q` is the JSON body from GET queue-status (200).
 */
export function presentationFromQueueStatus(q: RunQueueStatusResponse): OperatorQueuePresentation {
  if (q.pipeline === 'heuristic') {
    const extra = q.detail ? ` ${q.detail}` : ''
    return {
      kind: 'heuristic_no_rq',
      badge: 'Heuristic (no queue)',
      description: `No Redis/RQ for this run (heuristic-only pipeline).${extra}`.trim(),
    }
  }

  const hasDetail = q.detail != null && q.detail.trim() !== ''

  if (q.requeue_eligible) {
    const rs = q.run_status.replace(/_/g, ' ')
    const suffix = recoveryReadySuffix(q)
    return {
      kind: 'full_recovery_ready',
      badge: `Recovery: can requeue${suffix}`,
      description: `POST /requeue is structurally allowed and no worker lock is held. Run row status: ${rs}. After requeue, refresh queue status (and the list here) to see updates.${q.job_id || q.rq_job_status ? ` Job id: ${formatQueueField(q.job_id)}.` : ''}`.trim(),
    }
  }

  if (q.lock_present) {
    const d = q.detail ? ` ${q.detail}` : ''
    return {
      kind: 'full_lock_blocks_requeue',
      badge: 'Blocked: worker lock',
      description: `A full-run Redis lock exists — POST /requeue returns 409 until it clears or expires.${d}`.trim(),
    }
  }

  if (hasDetail) {
    return {
      kind: 'full_not_eligible',
      badge: 'Not requeue-eligible',
      description: q.detail!.trim(),
    }
  }

  return {
    kind: 'full_ineligible_no_detail',
    badge: 'Not requeue-eligible',
    description:
      'Requeue is not eligible, but the server returned no lock and no detail — retry queue status or open run detail.',
  }
}

export function presentationFromRowState(remote: QueueRowRemoteState): OperatorQueuePresentation {
  switch (remote.phase) {
    case 'not_fetched':
      return {
        kind: 'need_queue_status',
        badge: 'Queue status needed',
        description: 'Click “Queue status” to load Redis/RQ fields and requeue eligibility.',
      }
    case 'loading':
      return {
        kind: 'loading',
        badge: 'Loading…',
        description: 'Fetching GET /runs/{id}/queue-status…',
      }
    case 'error':
      return {
        kind: 'error',
        badge: 'Queue status error',
        description: remote.message,
      }
    case 'ok':
      return presentationFromQueueStatus(remote.q)
    default:
      return {
        kind: 'error',
        badge: 'Unknown',
        description: 'Unexpected queue row state.',
      }
  }
}

/** CSS modifier (use as `cl-queue-op--${modifier}`). */
export function operatorBadgeModifier(p: OperatorQueuePresentation): string {
  switch (p.kind) {
    case 'need_queue_status':
      return 'muted'
    case 'loading':
      return 'loading'
    case 'error':
      return 'error'
    case 'heuristic_no_rq':
      return 'heuristic'
    case 'full_recovery_ready':
      return 'recovery'
    case 'full_lock_blocks_requeue':
      return 'lock'
    case 'full_not_eligible':
    case 'full_ineligible_no_detail':
      return 'ineligible'
    default:
      return 'muted'
  }
}
