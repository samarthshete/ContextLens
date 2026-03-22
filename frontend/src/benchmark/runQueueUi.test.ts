import { describe, expect, it } from 'vitest'
import type { RunQueueStatusResponse } from '../api/types'
import { formatQueueField, shouldShowRequeueButton } from './runQueueUi'

function base(over: Partial<RunQueueStatusResponse>): RunQueueStatusResponse {
  return {
    run_id: 1,
    run_status: 'running',
    pipeline: 'full',
    job_id: null,
    rq_job_status: null,
    lock_present: false,
    requeue_eligible: false,
    detail: null,
    ...over,
  }
}

describe('shouldShowRequeueButton', () => {
  it('is false for heuristic pipeline', () => {
    expect(shouldShowRequeueButton(base({ pipeline: 'heuristic', requeue_eligible: true }))).toBe(
      false,
    )
  })
  it('is false when full but not eligible', () => {
    expect(shouldShowRequeueButton(base({ pipeline: 'full', requeue_eligible: false }))).toBe(false)
  })
  it('is true when full and eligible', () => {
    expect(shouldShowRequeueButton(base({ pipeline: 'full', requeue_eligible: true }))).toBe(true)
  })
  it('is false for completed-style full payload (requeue_eligible false, rq finished)', () => {
    expect(
      shouldShowRequeueButton(
        base({
          pipeline: 'full',
          requeue_eligible: false,
          rq_job_status: 'finished',
          run_status: 'completed',
        }),
      ),
    ).toBe(false)
  })
})

describe('formatQueueField', () => {
  it('returns em dash for null/empty', () => {
    expect(formatQueueField(null)).toBe('—')
    expect(formatQueueField(undefined)).toBe('—')
    expect(formatQueueField('')).toBe('—')
  })
  it('returns string as-is', () => {
    expect(formatQueueField('queued')).toBe('queued')
  })
})
