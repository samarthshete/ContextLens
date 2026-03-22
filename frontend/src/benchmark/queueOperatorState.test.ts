import { describe, expect, it } from 'vitest'
import type { RunQueueStatusResponse } from '../api/types'
import {
  operatorBadgeModifier,
  parseQueueRowRemoteState,
  presentationFromQueueStatus,
  presentationFromRowState,
} from './queueOperatorState'

function full(over: Partial<RunQueueStatusResponse>): RunQueueStatusResponse {
  return {
    run_id: 1,
    run_status: 'running',
    pipeline: 'full',
    job_id: 'j',
    rq_job_status: 'queued',
    lock_present: false,
    requeue_eligible: true,
    detail: null,
    ...over,
  }
}

describe('queueOperatorState', () => {
  it('parseQueueRowRemoteState covers not_fetched, loading, error, ok', () => {
    expect(parseQueueRowRemoteState(undefined).phase).toBe('not_fetched')
    expect(parseQueueRowRemoteState({ loading: true, data: null, error: null }).phase).toBe('loading')
    expect(
      parseQueueRowRemoteState({ loading: false, data: null, error: 'x' }).phase,
    ).toBe('error')
    const q = full({})
    expect(parseQueueRowRemoteState({ loading: false, data: q, error: null }).phase).toBe('ok')
  })

  it('presentationFromRowState maps remote phases safely', () => {
    expect(presentationFromRowState({ phase: 'not_fetched' }).kind).toBe('need_queue_status')
    expect(presentationFromRowState({ phase: 'loading' }).kind).toBe('loading')
    expect(presentationFromRowState({ phase: 'error', message: '503' }).description).toContain('503')
    expect(presentationFromRowState({ phase: 'ok', q: full({ requeue_eligible: true }) }).kind).toBe(
      'full_recovery_ready',
    )
  })

  it('heuristic pipeline shows heuristic badge and optional detail', () => {
    const a = presentationFromQueueStatus({
      run_id: 1,
      run_status: 'completed',
      pipeline: 'heuristic',
      job_id: null,
      rq_job_status: null,
      lock_present: false,
      requeue_eligible: false,
      detail: 'struct note',
    })
    expect(a.kind).toBe('heuristic_no_rq')
    expect(a.badge).toContain('Heuristic')
    expect(a.description).toContain('struct note')

    const b = presentationFromQueueStatus({
      run_id: 1,
      run_status: 'completed',
      pipeline: 'heuristic',
      job_id: null,
      rq_job_status: null,
      lock_present: false,
      requeue_eligible: false,
      detail: null,
    })
    expect(b.description).not.toContain('struct')
  })

  it('full recovery_ready reflects RQ suffixes', () => {
    expect(presentationFromQueueStatus(full({ rq_job_status: 'queued', requeue_eligible: true })).badge).toMatch(
      /RQ: queued/,
    )
    expect(presentationFromQueueStatus(full({ rq_job_status: 'started', requeue_eligible: true })).badge).toMatch(
      /RQ: running/,
    )
    expect(presentationFromQueueStatus(full({ rq_job_status: 'finished', requeue_eligible: true })).badge).toMatch(
      /RQ: finished/,
    )
    expect(presentationFromQueueStatus(full({ rq_job_status: 'failed', requeue_eligible: true })).badge).toMatch(
      /terminal/,
    )
    expect(
      presentationFromQueueStatus(
        full({ job_id: null, rq_job_status: null, requeue_eligible: true }),
      ).badge,
    ).toMatch(/not visible/)
  })

  it('full lock blocks before detail-only ineligible', () => {
    const p = presentationFromQueueStatus(
      full({
        requeue_eligible: false,
        lock_present: true,
        detail: 'A full-run worker lock is held',
      }),
    )
    expect(p.kind).toBe('full_lock_blocks_requeue')
    expect(p.badge).toMatch(/lock/i)
    expect(operatorBadgeModifier(p)).toBe('lock')
  })

  it('full not eligible uses API detail when no lock', () => {
    const p = presentationFromQueueStatus(
      full({
        requeue_eligible: false,
        lock_present: false,
        detail: 'Run is completed',
      }),
    )
    expect(p.kind).toBe('full_not_eligible')
    expect(p.description).toContain('completed')
  })

  it('full ineligible with empty detail is safe unknown copy', () => {
    const p = presentationFromQueueStatus(
      full({
        requeue_eligible: false,
        lock_present: false,
        detail: '  ',
      }),
    )
    expect(p.kind).toBe('full_ineligible_no_detail')
    expect(p.description).toMatch(/retry queue status/i)
  })

  it('operatorBadgeModifier covers kinds', () => {
    expect(operatorBadgeModifier(presentationFromRowState({ phase: 'not_fetched' }))).toBe('muted')
    expect(operatorBadgeModifier(presentationFromRowState({ phase: 'loading' }))).toBe('loading')
    expect(
      operatorBadgeModifier(
        presentationFromQueueStatus(
          full({ requeue_eligible: false, lock_present: false, detail: 'x' }),
        ),
      ),
    ).toBe('ineligible')
  })
})
