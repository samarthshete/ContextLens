/** @vitest-environment jsdom */
import '@testing-library/jest-dom/vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from '../App'
import type { RunListItem } from '../api/types'

vi.mock('../api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/client')>()
  return {
    ...actual,
    api: {
      ...actual.api,
      listDatasets: vi.fn().mockResolvedValue([{ id: 1, name: 'DS1', description: null, created_at: 't' }]),
      listPipelineConfigs: vi.fn().mockResolvedValue([
        {
          id: 2,
          name: 'PC2',
          embedding_model: 'm',
          chunk_strategy: 'fixed',
          chunk_size: 256,
          chunk_overlap: 0,
          top_k: 5,
          created_at: 't',
        },
      ]),
      listDocuments: vi.fn().mockResolvedValue([]),
      listQueryCases: vi.fn().mockResolvedValue([]),
      listRuns: vi.fn().mockResolvedValue({ items: [], total: 0, limit: 25, offset: 0 }),
      getRun: vi.fn(async (id: number) => ({
        run_id: id,
        status: 'completed',
        evaluator_type: 'heuristic',
        created_at: '2026-01-01T00:00:00Z',
        retrieval_latency_ms: 1,
        generation_latency_ms: null,
        evaluation_latency_ms: 1,
        total_latency_ms: 2,
        query_case: { id: 1, dataset_id: 1, query_text: 'q', expected_answer: null },
        pipeline_config: {
          id: 2,
          name: 'PC2',
          embedding_model: 'm',
          chunk_strategy: 'fixed',
          top_k: 5,
        },
        retrieval_hits: [],
        generation: null,
        evaluation: null,
      })),
      dashboardSummary: vi.fn().mockResolvedValue({
        total_runs: 0,
        scale: {
          benchmark_datasets: 0,
          total_queries: 0,
          total_traced_runs: 0,
          configs_tested: 0,
          documents_processed: 0,
          chunks_indexed: 0,
        },
        status_counts: { completed: 0, failed: 0, in_progress: 0 },
        evaluator_counts: { heuristic_runs: 0, llm_runs: 0, runs_without_evaluation: 0 },
        latency: {
          avg_retrieval_latency_ms: null,
          retrieval_latency_p50_ms: null,
          retrieval_latency_p95_ms: null,
          avg_generation_latency_ms: null,
          avg_evaluation_latency_ms: null,
          avg_total_latency_ms: null,
          end_to_end_run_latency_avg_sec: null,
          end_to_end_run_latency_p95_sec: null,
        },
        cost: {
          total_cost_usd: null,
          avg_cost_usd: null,
          evaluation_rows_with_cost: 0,
          evaluation_rows_cost_not_available: 0,
          avg_cost_usd_per_llm_run: null,
          llm_runs_with_measured_cost: 0,
          avg_cost_usd_per_full_rag_run: null,
          full_rag_runs_with_measured_cost: 0,
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
        end_to_end_run_latency_avg_sec: null,
        end_to_end_run_latency_p95_sec: null,
        failure_analysis: { overall_counts: {}, overall_percentages: {}, by_config: [], recent_failed_runs: [] },
        config_insights: [],
      }),
      configComparison: vi.fn().mockResolvedValue({
        evaluator_type: 'both',
        pipeline_config_ids: [],
        configs: null,
        buckets: { heuristic: [], llm: [] },
        score_comparison: null,
        score_comparison_buckets: {
          heuristic: {
            best_config_faithfulness: null,
            worst_config_faithfulness: null,
            faithfulness_delta_pct: null,
            best_config_completeness: null,
            worst_config_completeness: null,
            completeness_delta_pct: null,
          },
          llm: {
            best_config_faithfulness: null,
            worst_config_faithfulness: null,
            faithfulness_delta_pct: null,
            best_config_completeness: null,
            worst_config_completeness: null,
            completeness_delta_pct: null,
          },
        },
      }),
    },
  }
})

import { api } from '../api/client'

const baseItem = (over: Partial<RunListItem> & Pick<RunListItem, 'run_id' | 'query_text'>): RunListItem => ({
  status: 'completed',
  created_at: '2026-01-01T00:00:00Z',
  dataset_id: 1,
  query_case_id: 1,
  pipeline_config_id: 2,
  retrieval_latency_ms: null,
  generation_latency_ms: null,
  evaluation_latency_ms: null,
  total_latency_ms: null,
  evaluator_type: 'heuristic',
  has_evaluation: true,
  ...over,
})

function renderRuns() {
  return render(
    <MemoryRouter initialEntries={['/runs']}>
      <Routes>
        <Route path="/runs/:runId" element={<App view="detail" />} />
        <Route path="/runs" element={<App view="runs" />} />
        <Route path="/benchmark" element={<App view="run" />} />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(api.listRuns).mockResolvedValue({
    items: [
      baseItem({ run_id: 10, query_text: 'unique alpha phrase' }),
      baseItem({ run_id: 20, query_text: 'beta other', evaluator_type: 'llm' }),
    ],
    total: 2,
    limit: 25,
    offset: 0,
  })
})

afterEach(() => {
  cleanup()
})

describe('runs list page filters', () => {
  it('shows filter bar on /runs', async () => {
    renderRuns()
    await waitFor(() => {
      expect(screen.getByTestId('runs-filter-bar')).toBeInTheDocument()
    })
  })

  it('refetches when status filter changes', async () => {
    renderRuns()
    await waitFor(() => expect(api.listRuns).toHaveBeenCalled())
    vi.mocked(api.listRuns).mockClear()
    fireEvent.change(screen.getByTestId('runs-filter-status'), { target: { value: 'failed' } })
    await waitFor(() => {
      expect(api.listRuns).toHaveBeenCalledWith(
        expect.objectContaining({ status: 'failed', limit: 25, offset: 0 }),
      )
    })
  })

  it('refetches when evaluator filter changes', async () => {
    renderRuns()
    await waitFor(() => expect(api.listRuns).toHaveBeenCalled())
    vi.mocked(api.listRuns).mockClear()
    fireEvent.change(screen.getByTestId('runs-filter-evaluator'), { target: { value: 'llm' } })
    await waitFor(() => {
      expect(api.listRuns).toHaveBeenCalledWith(
        expect.objectContaining({ evaluator_type: 'llm', limit: 25, offset: 0 }),
      )
    })
  })

  it('refetches when dataset filter changes', async () => {
    renderRuns()
    await waitFor(() => expect(api.listRuns).toHaveBeenCalled())
    vi.mocked(api.listRuns).mockClear()
    fireEvent.change(screen.getByTestId('runs-filter-dataset'), { target: { value: '1' } })
    await waitFor(() => {
      expect(api.listRuns).toHaveBeenCalledWith(
        expect.objectContaining({ dataset_id: 1, limit: 25, offset: 0 }),
      )
    })
  })

  it('refetches when pipeline filter changes', async () => {
    renderRuns()
    await waitFor(() => expect(api.listRuns).toHaveBeenCalled())
    vi.mocked(api.listRuns).mockClear()
    fireEvent.change(screen.getByTestId('runs-filter-pipeline'), { target: { value: '2' } })
    await waitFor(() => {
      expect(api.listRuns).toHaveBeenCalledWith(
        expect.objectContaining({ pipeline_config_id: 2, limit: 25, offset: 0 }),
      )
    })
  })

  it('clear filters resets server params on next fetch', async () => {
    renderRuns()
    await waitFor(() => expect(api.listRuns).toHaveBeenCalled())
    fireEvent.change(screen.getByTestId('runs-filter-status'), { target: { value: 'completed' } })
    await waitFor(() =>
      expect(vi.mocked(api.listRuns).mock.calls.some((c) => (c[0] as { status?: string })?.status === 'completed')).toBe(
        true,
      ),
    )
    vi.mocked(api.listRuns).mockClear()
    fireEvent.click(screen.getByTestId('runs-filter-clear'))
    await waitFor(() => {
      const last = vi.mocked(api.listRuns).mock.calls.at(-1)?.[0] as Record<string, unknown>
      expect(last).toEqual({ limit: 25, offset: 0 })
    })
  })

  it('narrow input hides non-matching loaded rows', async () => {
    renderRuns()
    await waitFor(() => {
      expect(screen.getAllByRole('button', { name: 'Open' })).toHaveLength(2)
    })
    fireEvent.change(screen.getByTestId('runs-filter-narrow'), { target: { value: 'alpha' } })
    await waitFor(() => {
      expect(screen.getAllByRole('button', { name: 'Open' })).toHaveLength(1)
    })
  })

  it('navigates to run detail when Open is clicked', async () => {
    renderRuns()
    await waitFor(() => {
      expect(screen.getAllByRole('button', { name: 'Open' })).toHaveLength(2)
    })
    fireEvent.click(screen.getAllByRole('button', { name: 'Open' })[0])
    await waitFor(() => {
      expect(api.getRun).toHaveBeenCalledWith(10)
    })
    await waitFor(() => {
      const input = screen.getByLabelText('Run ID') as HTMLInputElement
      expect(input.value).toBe('10')
    })
  })
})
