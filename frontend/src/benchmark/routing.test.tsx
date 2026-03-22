/** @vitest-environment jsdom */
import '@testing-library/jest-dom/vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from '../App'

// Mock the API so BenchmarkWorkspace doesn't make real requests
vi.mock('../api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/client')>()
  return {
    ...actual,
    api: {
      ...actual.api,
      listDatasets: vi.fn().mockResolvedValue([]),
      listPipelineConfigs: vi.fn().mockResolvedValue([]),
      listDocuments: vi.fn().mockResolvedValue([]),
      getDocument: vi.fn().mockResolvedValue({
        id: 1,
        title: 'Test doc',
        source_type: 'md',
        status: 'processed',
        created_at: '2026-01-01T00:00:00.000Z',
        metadata_json: null,
      }),
      getDocumentChunks: vi.fn().mockResolvedValue([]),
      listQueryCases: vi.fn().mockResolvedValue([]),
      listRuns: vi.fn().mockResolvedValue({ items: [], total: 0, limit: 25, offset: 0 }),
      getRun: vi.fn(),
      dashboardSummary: vi.fn().mockResolvedValue({
        total_runs: 0,
        status_counts: { completed: 0, failed: 0, in_progress: 0 },
        evaluator_counts: { heuristic_runs: 0, llm_runs: 0, runs_without_evaluation: 0 },
        latency: {
          avg_retrieval_latency_ms: null,
          avg_generation_latency_ms: null,
          avg_evaluation_latency_ms: null,
          avg_total_latency_ms: null,
        },
        cost: {
          total_cost_usd: null,
          avg_cost_usd: null,
          evaluation_rows_with_cost: 0,
          evaluation_rows_cost_not_available: 0,
        },
        failure_type_counts: {},
        recent_runs: [],
      }),
      dashboardAnalytics: vi.fn().mockResolvedValue({
        time_series: [],
        latency_distribution: {
          retrieval: { count: 0, min_ms: null, max_ms: null, avg_ms: null, median_ms: null, p95_ms: null },
          generation: { count: 0, min_ms: null, max_ms: null, avg_ms: null, median_ms: null, p95_ms: null },
          evaluation: { count: 0, min_ms: null, max_ms: null, avg_ms: null, median_ms: null, p95_ms: null },
          total: { count: 0, min_ms: null, max_ms: null, avg_ms: null, median_ms: null, p95_ms: null },
        },
        failure_analysis: { overall_counts: {}, overall_percentages: {}, by_config: [], recent_failed_runs: [] },
        config_insights: [],
      }),
      configComparison: vi.fn().mockResolvedValue({ buckets: { heuristic: [], llm: [] } }),
    },
  }
})

import { api } from '../api/client'

function renderWithRoute(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/benchmark" element={<App view="run" />} />
        <Route path="/runs/:runId" element={<App view="detail" />} />
        <Route path="/runs" element={<App view="runs" />} />
        <Route path="/queue" element={<App view="queue" />} />
        <Route path="/compare" element={<App view="compare" />} />
        <Route path="/dashboard" element={<App view="dashboard" />} />
        <Route path="/documents/:documentId" element={<App view="document" />} />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
})

afterEach(() => {
  cleanup()
})

describe('client-side routing', () => {
  it('/benchmark renders the Run benchmark view', async () => {
    renderWithRoute('/benchmark')
    await waitFor(() => {
      expect(screen.getByText('How to run a benchmark')).toBeInTheDocument()
    })
  })

  it('/runs renders the Recent runs view', async () => {
    renderWithRoute('/runs')
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Recent runs', level: 2 })).toBeInTheDocument()
    })
  })

  it('/queue renders the Queue browser view', async () => {
    renderWithRoute('/queue')
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Queue browser', level: 2 })).toBeInTheDocument()
    })
  })

  it('/compare renders the Config comparison view', async () => {
    renderWithRoute('/compare')
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Config comparison', level: 2 })).toBeInTheDocument()
    })
  })

  it('/dashboard renders the Dashboard observability view', async () => {
    renderWithRoute('/dashboard')
    await waitFor(() => {
      // DashboardPanel renders "Observability" as its main heading
      expect(screen.getByRole('heading', { name: 'Observability', level: 2 })).toBeInTheDocument()
    })
  })

  it('/documents/:documentId renders document detail', async () => {
    renderWithRoute('/documents/1')
    await waitFor(() => {
      expect(screen.getByTestId('document-detail-panel')).toBeInTheDocument()
    })
    await waitFor(() => {
      expect(screen.getByTestId('document-detail-meta')).toHaveTextContent('Test doc')
    })
    expect(api.getDocument).toHaveBeenCalledWith(1)
    expect(api.getDocumentChunks).toHaveBeenCalledWith(1)
  })

  it('/runs/:runId loads run detail with the correct run id', async () => {
    const mockDetail = {
      run_id: 42,
      status: 'completed',
      evaluator_type: 'heuristic',
      created_at: '2026-01-01T00:00:00Z',
      retrieval_latency_ms: 10,
      generation_latency_ms: null,
      evaluation_latency_ms: 5,
      total_latency_ms: 15,
      query_case: { id: 1, dataset_id: 1, query_text: 'test query', expected_answer: null },
      pipeline_config: {
        id: 1,
        name: 'default',
        embedding_model: 'test',
        chunk_strategy: 'fixed',
        chunk_size: 256,
        chunk_overlap: 0,
        top_k: 5,
      },
      retrieval_hits: [],
      generation: null,
      evaluation: null,
    }
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    vi.mocked(api.getRun).mockResolvedValue(mockDetail as any)

    renderWithRoute('/runs/42')
    await waitFor(() => {
      expect(screen.getByLabelText('Run ID')).toBeInTheDocument()
    })
    const input = screen.getByLabelText('Run ID') as HTMLInputElement
    expect(input.value).toBe('42')
    expect(api.getRun).toHaveBeenCalledWith(42)
    await waitFor(() => {
      expect(screen.getByTestId('run-diagnosis-summary')).toBeInTheDocument()
    })

    const exportBtn = screen.getByTestId('run-export-json')
    expect(exportBtn).toHaveAccessibleName(/export json/i)

    const prevCreate = Object.getOwnPropertyDescriptor(URL, 'createObjectURL')
    const prevRevoke = Object.getOwnPropertyDescriptor(URL, 'revokeObjectURL')
    const createUrl = vi.fn(() => 'blob:run-export-test')
    const revokeUrl = vi.fn()
    Object.defineProperty(URL, 'createObjectURL', {
      configurable: true,
      writable: true,
      value: createUrl,
    })
    Object.defineProperty(URL, 'revokeObjectURL', {
      configurable: true,
      writable: true,
      value: revokeUrl,
    })

    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})

    try {
      fireEvent.click(exportBtn)

      await waitFor(() => {
        expect(createUrl).toHaveBeenCalled()
      })
      const calls = createUrl.mock.calls as unknown as [Blob][]
      const blob = calls[0][0]
      expect(blob).toBeInstanceOf(Blob)
      const text = await blob.text()
      expect(JSON.parse(text).run_id).toBe(42)

      expect(click).toHaveBeenCalled()
      expect(revokeUrl).toHaveBeenCalledWith('blob:run-export-test')
    } finally {
      click.mockRestore()
      if (prevCreate) {
        Object.defineProperty(URL, 'createObjectURL', prevCreate)
      } else {
        delete (URL as unknown as { createObjectURL?: unknown }).createObjectURL
      }
      if (prevRevoke) {
        Object.defineProperty(URL, 'revokeObjectURL', prevRevoke)
      } else {
        delete (URL as unknown as { revokeObjectURL?: unknown }).revokeObjectURL
      }
    }
  })

  it('/runs/:runId with non-numeric ID shows invalid ID error', async () => {
    renderWithRoute('/runs/abc')
    await waitFor(() => {
      expect(screen.getByText(/Invalid run ID/)).toBeInTheDocument()
    })
    expect(screen.getByText(/abc/)).toBeInTheDocument()
  })

  it('nav buttons reflect active view from URL', async () => {
    renderWithRoute('/compare')
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Config comparison', level: 2 })).toBeInTheDocument()
    })
    // Config comparison nav button should be active
    const compareBtn = screen.getByRole('button', { name: 'Config comparison' })
    expect(compareBtn).toHaveAttribute('data-active', 'true')
    // Other nav buttons should be inactive
    const runsBtn = screen.getAllByRole('button', { name: 'Recent runs' })[0]
    expect(runsBtn).toHaveAttribute('data-active', 'false')
  })
})
