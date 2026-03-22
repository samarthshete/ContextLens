/** @vitest-environment jsdom */
import '@testing-library/jest-dom/vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { RunDetail } from '../api/types'
import { RunDiffPanel } from './RunDiffPanel'

vi.mock('../api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/client')>()
  return {
    ...actual,
    api: {
      ...actual.api,
      getRun: vi.fn(),
    },
  }
})

import { api } from '../api/client'

const baseRun: RunDetail = {
  run_id: 101,
  status: 'completed',
  created_at: '2026-01-01T00:00:00Z',
  retrieval_latency_ms: 1,
  generation_latency_ms: null,
  evaluation_latency_ms: 1,
  total_latency_ms: 2,
  evaluator_type: 'heuristic',
  query_case: { id: 1, dataset_id: 1, query_text: 'q', expected_answer: null },
  pipeline_config: {
    id: 1,
    name: 'p',
    embedding_model: 'm',
    chunk_strategy: 'fixed',
    chunk_size: 256,
    chunk_overlap: 0,
    top_k: 5,
  },
  retrieval_hits: [{ rank: 1, score: 0.2, chunk_id: 1, document_id: 1, content: 'x', chunk_index: 0 }],
  generation: null,
  evaluation: { failure_type: 'NO_FAILURE', used_llm_judge: false },
}

const otherRun: RunDetail = {
  ...baseRun,
  run_id: 102,
  retrieval_hits: [
    { rank: 1, score: 0.9, chunk_id: 2, document_id: 1, content: 'ab', chunk_index: 0 },
    { rank: 2, score: 0.8, chunk_id: 3, document_id: 1, content: 'cd', chunk_index: 1 },
  ],
}

describe('RunDiffPanel', () => {
  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  it('shows empty hint before load', () => {
    render(<RunDiffPanel baseRun={baseRun} />)
    expect(screen.getByTestId('run-diff-panel')).toBeInTheDocument()
    expect(screen.getByText(/Enter a run ID and load/i)).toBeInTheDocument()
  })

  it('loads comparison run and renders summary + table', async () => {
    vi.mocked(api.getRun).mockResolvedValue(otherRun)

    render(<RunDiffPanel baseRun={baseRun} />)
    fireEvent.change(screen.getByLabelText(/Compare with run ID/i), { target: { value: '102' } })
    fireEvent.click(screen.getByRole('button', { name: /Load comparison/i }))

    await waitFor(() => {
      expect(api.getRun).toHaveBeenCalledWith(102)
    })
    await waitFor(() => {
      expect(screen.getByTestId('run-diff-summary')).toBeInTheDocument()
    })
    expect(screen.getByRole('columnheader', { name: /Run A/i })).toBeInTheDocument()
    expect(screen.getByRole('table')).toHaveTextContent('102')
  })

  it('rejects same run id as base', async () => {
    render(<RunDiffPanel baseRun={baseRun} />)
    fireEvent.change(screen.getByLabelText(/Compare with run ID/i), { target: { value: '101' } })
    fireEvent.click(screen.getByRole('button', { name: /Load comparison/i }))
    expect(api.getRun).not.toHaveBeenCalled()
    expect(screen.getByRole('alert')).toHaveTextContent(/different run ID/i)
  })
})
