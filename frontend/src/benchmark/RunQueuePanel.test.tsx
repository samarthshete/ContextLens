/** @vitest-environment jsdom */
import '@testing-library/jest-dom/vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '../api/client'
import type { RunQueueStatusResponse } from '../api/types'
import { RunQueuePanel } from './RunQueuePanel'

vi.mock('../api/client', () => ({
  api: {
    getRunQueueStatus: vi.fn(),
    requeueRun: vi.fn(),
  },
}))

const getRunQueueStatus = vi.mocked(api.getRunQueueStatus)

function fullQueue(over: Partial<RunQueueStatusResponse>): RunQueueStatusResponse {
  return {
    run_id: 2,
    run_status: 'completed',
    pipeline: 'full',
    job_id: 'job-1',
    rq_job_status: 'finished',
    lock_present: false,
    requeue_eligible: false,
    detail: null,
    ...over,
  }
}

describe('RunQueuePanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('hides Requeue after runStatus changes when queue-status becomes ineligible', async () => {
    getRunQueueStatus
      .mockResolvedValueOnce(
        fullQueue({
          run_status: 'running',
          requeue_eligible: true,
          rq_job_status: 'queued',
        }),
      )
      .mockResolvedValueOnce(
        fullQueue({
          run_status: 'completed',
          requeue_eligible: false,
          rq_job_status: 'finished',
          detail: 'Run is completed — not eligible for requeue.',
        }),
      )

    const { rerender } = render(<RunQueuePanel runId={2} runStatus="running" />)

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /requeue full run/i })).toBeInTheDocument()
    })
    expect(screen.getByTestId('run-queue-operator-readout')).toHaveTextContent(/Recovery: can requeue/i)

    rerender(<RunQueuePanel runId={2} runStatus="completed" />)

    await waitFor(() => {
      expect(screen.queryByRole('button', { name: /requeue full run/i })).not.toBeInTheDocument()
    })
    expect(screen.getByTestId('run-queue-operator-readout')).toHaveTextContent(/Not requeue-eligible/i)
    const eligibleRow = screen.getByText('Requeue eligible').closest('.cl-queue-row')
    expect(eligibleRow).toHaveTextContent(/no/)
    expect(screen.getByText('RQ job status').closest('.cl-queue-row')).toHaveTextContent(/finished/)
  })

  it('refetches queue-status when runId changes (no stale run)', async () => {
    getRunQueueStatus
      .mockResolvedValueOnce(
        fullQueue({ run_id: 1, run_status: 'completed', requeue_eligible: false }),
      )
      .mockResolvedValueOnce(
        fullQueue({
          run_id: 3,
          run_status: 'running',
          requeue_eligible: true,
          job_id: 'other',
        }),
      )

    const { rerender } = render(<RunQueuePanel runId={1} runStatus="completed" />)

    await waitFor(() => {
      expect(getRunQueueStatus).toHaveBeenCalledWith(1)
    })

    rerender(<RunQueuePanel runId={3} runStatus="running" />)

    await waitFor(() => {
      expect(getRunQueueStatus).toHaveBeenCalledWith(3)
    })
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /requeue full run/i })).toBeInTheDocument()
    })
  })
})
