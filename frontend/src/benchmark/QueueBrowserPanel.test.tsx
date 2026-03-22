/** @vitest-environment jsdom */
import '@testing-library/jest-dom/vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { QueueBrowserPanel } from './QueueBrowserPanel'
import { QUEUE_BROWSER_STATUS_SLICES } from './queueBrowserLoad'
import type { RunListItem } from '../api/types'

vi.mock('../api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/client')>()
  return {
    ...actual,
    api: {
      ...actual.api,
      listRuns: vi.fn(),
      getRunQueueStatus: vi.fn(),
      requeueRun: vi.fn(),
    },
  }
})

import { api } from '../api/client'

const baseRow = (over: Partial<RunListItem> & Pick<RunListItem, 'run_id'>): RunListItem => ({
  status: 'running',
  created_at: '2026-01-01T00:00:00Z',
  dataset_id: 1,
  query_case_id: 1,
  pipeline_config_id: 1,
  query_text: 'q',
  retrieval_latency_ms: null,
  generation_latency_ms: null,
  evaluation_latency_ms: null,
  total_latency_ms: null,
  evaluator_type: 'none',
  has_evaluation: false,
  ...over,
})

function renderPanel(path = '/queue') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route
          path="/queue"
          element={<QueueBrowserPanel pipelineConfigs={[{ id: 1, name: 'P1', embedding_model: 'm', chunk_strategy: 'fixed', chunk_size: 256, chunk_overlap: 0, top_k: 5, created_at: 't' }]} registryLoading={false} />}
        />
        <Route path="/runs/:runId" element={<div data-testid="run-detail-mock">detail</div>} />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(api.listRuns).mockImplementation(async (params) => {
    if (params?.status === 'running') {
      return {
        items: [baseRow({ run_id: 42, evaluator_type: 'none' })],
        total: 1,
        limit: 20,
        offset: 0,
      }
    }
    return { items: [], total: 0, limit: 20, offset: 0 }
  })
})

afterEach(() => {
  cleanup()
})

describe('QueueBrowserPanel', () => {
  it('renders heading and loads rows', async () => {
    renderPanel()
    expect(screen.getByTestId('queue-browser')).toBeInTheDocument()
    await waitFor(() => {
      expect(screen.getByTestId('queue-browser-row-42')).toBeInTheDocument()
    })
    expect(screen.getByTestId('queue-browser-op-badge-42')).toHaveTextContent(/Queue status needed/i)
    expect(api.listRuns).toHaveBeenCalled()
    expect(vi.mocked(api.listRuns).mock.calls.length).toBe(QUEUE_BROWSER_STATUS_SLICES.length)
  })

  it('fetches queue status on row button and shows heuristic note', async () => {
    vi.mocked(api.getRunQueueStatus).mockResolvedValue({
      run_id: 42,
      run_status: 'running',
      pipeline: 'heuristic',
      job_id: null,
      rq_job_status: null,
      lock_present: false,
      requeue_eligible: false,
      detail: null,
    })
    renderPanel()
    await waitFor(() => expect(screen.getByTestId('queue-browser-row-42')).toBeInTheDocument())
    fireEvent.click(screen.getByTestId('queue-browser-refresh-qs-42'))
    await waitFor(() => {
      expect(api.getRunQueueStatus).toHaveBeenCalledWith(42)
    })
    expect(screen.getByTestId('queue-browser-heuristic-42')).toHaveTextContent(/no RQ/i)
    expect(screen.getByTestId('queue-browser-op-badge-42')).toHaveTextContent(/Heuristic/i)
  })

  it('shows queue-status error in cell', async () => {
    vi.mocked(api.getRunQueueStatus).mockRejectedValue(new Error('503'))
    renderPanel()
    await waitFor(() => expect(screen.getByTestId('queue-browser-row-42')).toBeInTheDocument())
    fireEvent.click(screen.getByTestId('queue-browser-refresh-qs-42'))
    await waitFor(() => {
      expect(screen.getByTestId('queue-browser-op-badge-42')).toHaveTextContent(/error/i)
    })
    expect(screen.getByTestId('queue-browser-op-badge-42').getAttribute('title')).toMatch(/503/)
  })

  it('navigates to run detail on Open', async () => {
    renderPanel()
    await waitFor(() => expect(screen.getByTestId('queue-browser-row-42')).toBeInTheDocument())
    fireEvent.click(screen.getAllByRole('button', { name: 'Open' })[0])
    await waitFor(() => {
      expect(screen.getByTestId('run-detail-mock')).toBeInTheDocument()
    })
  })

  it('offers requeue when queue-status says eligible', async () => {
    vi.mocked(api.getRunQueueStatus).mockResolvedValue({
      run_id: 42,
      run_status: 'failed',
      pipeline: 'full',
      job_id: 'old',
      rq_job_status: 'failed',
      lock_present: false,
      requeue_eligible: true,
      detail: null,
    })
    vi.mocked(api.requeueRun).mockResolvedValue({ run_id: 42, status: 'running', job_id: 'newjob' })
    renderPanel()
    await waitFor(() => expect(screen.getByTestId('queue-browser-row-42')).toBeInTheDocument())
    fireEvent.click(screen.getByTestId('queue-browser-refresh-qs-42'))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Requeue' })).toBeInTheDocument())
    expect(screen.getByTestId('queue-browser-op-badge-42')).toHaveTextContent(/Recovery: can requeue/i)
    const listCallsBefore = vi.mocked(api.listRuns).mock.calls.length
    fireEvent.click(screen.getByRole('button', { name: 'Requeue' }))
    await waitFor(() => {
      expect(api.requeueRun).toHaveBeenCalledWith(42)
    })
    await waitFor(() => {
      expect(vi.mocked(api.listRuns).mock.calls.length).toBeGreaterThan(listCallsBefore)
    })
    await waitFor(() => {
      expect(screen.getByTestId('queue-browser-requeue-notice')).toHaveTextContent(/requeued/i)
    })
  })

  it('shows lock-blocked operator readout when lock present', async () => {
    vi.mocked(api.getRunQueueStatus).mockResolvedValue({
      run_id: 42,
      run_status: 'running',
      pipeline: 'full',
      job_id: 'j',
      rq_job_status: 'started',
      lock_present: true,
      requeue_eligible: false,
      detail: 'A full-run worker lock is held for this run_id; wait for it to finish or expire.',
    })
    renderPanel()
    await waitFor(() => expect(screen.getByTestId('queue-browser-row-42')).toBeInTheDocument())
    fireEvent.click(screen.getByTestId('queue-browser-refresh-qs-42'))
    await waitFor(() => {
      expect(screen.getByTestId('queue-browser-op-badge-42')).toHaveTextContent(/Blocked: worker lock/i)
    })
  })
})
