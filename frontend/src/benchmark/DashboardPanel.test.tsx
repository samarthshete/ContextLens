/** @vitest-environment jsdom */
import '@testing-library/jest-dom/vitest'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { ConfigComparisonMetrics, DashboardSummaryResponse } from '../api/types'
import { emptyConfigComparisonBoth, nullScoreSummary } from './configComparisonMock'
import { DashboardPanel } from './DashboardPanel'
import * as exportDownload from './exportDownload'

vi.mock('../api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/client')>()
  return {
    ...actual,
    api: {
      ...actual.api,
      dashboardSummary: vi.fn(),
      dashboardAnalytics: vi.fn(),
      configComparison: vi.fn(),
    },
  }
})

import { api } from '../api/client'

const dashboardSummary = vi.mocked(api.dashboardSummary)
const dashboardAnalytics = vi.mocked(api.dashboardAnalytics)
const configComparison = vi.mocked(api.configComparison)

function minimalAnalytics() {
  return {
    time_series: [],
    latency_distribution: {
      retrieval: { count: 0, min_ms: null, max_ms: null, avg_ms: null, median_ms: null, p95_ms: null },
      generation: { count: 0, min_ms: null, max_ms: null, avg_ms: null, median_ms: null, p95_ms: null },
      evaluation: { count: 0, min_ms: null, max_ms: null, avg_ms: null, median_ms: null, p95_ms: null },
      total: { count: 0, min_ms: null, max_ms: null, avg_ms: null, median_ms: null, p95_ms: null },
    },
    end_to_end_run_latency_avg_sec: null,
    end_to_end_run_latency_p95_sec: null,
    failure_analysis: {
      overall_counts: {},
      overall_percentages: {},
      by_config: [],
      recent_failed_runs: [],
    },
    config_insights: [],
  }
}

function minimalCompareRow(over: Partial<ConfigComparisonMetrics> = {}): ConfigComparisonMetrics {
  return {
    pipeline_config_id: 1,
    traced_runs: 0,
    avg_faithfulness: null,
    avg_retrieval_latency_ms: null,
    p95_retrieval_latency_ms: null,
    avg_evaluation_latency_ms: null,
    p95_evaluation_latency_ms: null,
    avg_total_latency_ms: null,
    p95_total_latency_ms: null,
    avg_groundedness: null,
    avg_completeness: null,
    avg_retrieval_relevance: null,
    avg_context_coverage: null,
    failure_type_counts: {},
    avg_evaluation_cost_per_run_usd: null,
    ...over,
  }
}

function minimalDashboard(over: Partial<DashboardSummaryResponse> = {}): DashboardSummaryResponse {
  return {
    total_runs: 1,
    scale: {
      benchmark_datasets: 1,
      total_queries: 3,
      total_traced_runs: 0,
      configs_tested: 1,
      documents_processed: 2,
      chunks_indexed: 8,
    },
    status_counts: { completed: 1, failed: 0, in_progress: 0 },
    evaluator_counts: { heuristic_runs: 1, llm_runs: 0, runs_without_evaluation: 0 },
    latency: {
      avg_retrieval_latency_ms: 10,
      retrieval_latency_p50_ms: 10,
      retrieval_latency_p95_ms: 10,
      avg_generation_latency_ms: null,
      avg_evaluation_latency_ms: 5,
      avg_total_latency_ms: 15,
      end_to_end_run_latency_avg_sec: 0.015,
      end_to_end_run_latency_p95_sec: 0.015,
    },
    cost: {
      total_cost_usd: null,
      avg_cost_usd: null,
      evaluation_rows_with_cost: 0,
      evaluation_rows_cost_not_available: 1,
      avg_cost_usd_per_llm_run: null,
      llm_runs_with_measured_cost: 0,
      avg_cost_usd_per_full_rag_run: null,
      full_rag_runs_with_measured_cost: 0,
    },
    failure_type_counts: {},
    recent_runs: [
      {
        run_id: 7,
        status: 'completed',
        created_at: '2026-01-01T00:00:00Z',
        evaluator_type: 'heuristic',
        total_latency_ms: 15,
        cost_usd: null,
        failure_type: 'UNKNOWN',
      },
    ],
    ...over,
  }
}

describe('DashboardPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  afterEach(() => {
    cleanup()
  })

  it('renders per-run LLM cost lines from dashboard summary', async () => {
    dashboardSummary.mockResolvedValue(
      minimalDashboard({
        cost: {
          total_cost_usd: 0.2,
          avg_cost_usd: 0.1,
          evaluation_rows_with_cost: 2,
          evaluation_rows_cost_not_available: 0,
          avg_cost_usd_per_llm_run: 0.1,
          llm_runs_with_measured_cost: 2,
          avg_cost_usd_per_full_rag_run: 0.15,
          full_rag_runs_with_measured_cost: 1,
        },
      }),
    )
    dashboardAnalytics.mockResolvedValue(minimalAnalytics())
    configComparison.mockResolvedValue(emptyConfigComparisonBoth({ pipeline_config_ids: [1] }))
    render(<DashboardPanel pipelineConfigIds={[1]} />)
    await waitFor(() => expect(screen.queryByText(/Loading dashboard/)).not.toBeInTheDocument())
    expect(screen.getByText(/Average per LLM run \(measured cost only\)/i)).toBeInTheDocument()
    expect(screen.getByText(/Average per full RAG run/i)).toBeInTheDocument()
    expect(screen.getByText(/\(2 runs with non-null cost/i)).toBeInTheDocument()
  })

  it('renders system scale metrics from dashboard summary', async () => {
    dashboardSummary.mockResolvedValue(minimalDashboard())
    dashboardAnalytics.mockResolvedValue(minimalAnalytics())
    configComparison.mockResolvedValue(emptyConfigComparisonBoth({ pipeline_config_ids: [1] }))
    render(<DashboardPanel pipelineConfigIds={[1]} />)
    await waitFor(() => expect(screen.queryByText(/Loading dashboard/)).not.toBeInTheDocument())
    const scale = screen.getByTestId('dashboard-system-scale')
    expect(within(scale).getByText('Benchmark datasets')).toBeInTheDocument()
    expect(within(scale).getByText('3')).toBeInTheDocument() // total_queries
    expect(within(scale).getByText('8')).toBeInTheDocument() // chunks_indexed
  })

  it('renders retrieval mean, P50, and P95 from dashboard summary', async () => {
    dashboardSummary.mockResolvedValue(
      minimalDashboard({
        latency: {
          avg_retrieval_latency_ms: 42,
          retrieval_latency_p50_ms: 40,
          retrieval_latency_p95_ms: 88,
          avg_generation_latency_ms: null,
          avg_evaluation_latency_ms: 5,
          avg_total_latency_ms: 120,
          end_to_end_run_latency_avg_sec: 0.12,
          end_to_end_run_latency_p95_sec: 0.12,
        },
      }),
    )
    dashboardAnalytics.mockResolvedValue(minimalAnalytics())
    configComparison.mockResolvedValue(emptyConfigComparisonBoth({ pipeline_config_ids: [1] }))
    render(<DashboardPanel pipelineConfigIds={[1]} />)
    await waitFor(() => expect(screen.queryByText(/Loading dashboard/)).not.toBeInTheDocument())
    const retrieval = screen.getByTestId('dashboard-retrieval-latency')
    expect(within(retrieval).getByText('42 ms')).toBeInTheDocument()
    expect(within(retrieval).getByText('40 ms')).toBeInTheDocument()
    expect(within(retrieval).getByText('88 ms')).toBeInTheDocument()
  })

  it('renders end-to-end mean (ms) and avg/p95 (s) from dashboard summary', async () => {
    dashboardSummary.mockResolvedValue(
      minimalDashboard({
        latency: {
          avg_retrieval_latency_ms: 10,
          retrieval_latency_p50_ms: 10,
          retrieval_latency_p95_ms: 10,
          avg_generation_latency_ms: null,
          avg_evaluation_latency_ms: 5,
          avg_total_latency_ms: 1500,
          end_to_end_run_latency_avg_sec: 1.5,
          end_to_end_run_latency_p95_sec: 2.25,
        },
      }),
    )
    dashboardAnalytics.mockResolvedValue(minimalAnalytics())
    configComparison.mockResolvedValue(emptyConfigComparisonBoth({ pipeline_config_ids: [1] }))
    render(<DashboardPanel pipelineConfigIds={[1]} />)
    await waitFor(() => expect(screen.queryByText(/Loading dashboard/)).not.toBeInTheDocument())
    const block = screen.getByTestId('dashboard-end-to-end-latency')
    expect(within(block).getByText('1500 ms')).toBeInTheDocument()
    expect(within(block).getByText('1.500 s')).toBeInTheDocument()
    expect(within(block).getByText('2.250 s')).toBeInTheDocument()
  })

  it('shows loading then summary cards from API', async () => {
    dashboardSummary.mockResolvedValue(minimalDashboard())
    dashboardAnalytics.mockResolvedValue(minimalAnalytics())
    configComparison.mockResolvedValue(emptyConfigComparisonBoth({ pipeline_config_ids: [1] }))

    render(<DashboardPanel pipelineConfigIds={[1]} />)

    expect(screen.getByText(/loading dashboard/i)).toBeInTheDocument()

    await waitFor(() => {
      expect(screen.getByText('Total runs')).toBeInTheDocument()
    })
    const totalCard = screen.getByText('Total runs').closest('.cl-dash-stat')
    expect(totalCard).toHaveTextContent('1')
    expect(screen.getByRole('heading', { name: 'Latency', level: 2 })).toBeInTheDocument()
    expect(screen.getByText(/recent runs/i)).toBeInTheDocument()
    expect(screen.getByRole('cell', { name: '7' })).toBeInTheDocument()
  })

  it('shows error when dashboardSummary fails', async () => {
    dashboardSummary.mockRejectedValue(new Error('network down'))
    dashboardAnalytics.mockResolvedValue(minimalAnalytics())

    render(<DashboardPanel pipelineConfigIds={[]} />)

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent(/network down/i)
    })
    expect(screen.getByTestId('dashboard-export-json')).toBeDisabled()
    expect(screen.getByTestId('dashboard-export-csv')).toBeDisabled()
  })

  it('shows empty failure section copy', async () => {
    dashboardSummary.mockResolvedValue(minimalDashboard({ failure_type_counts: {} }))
    dashboardAnalytics.mockResolvedValue(minimalAnalytics())

    render(<DashboardPanel pipelineConfigIds={[]} />)

    await waitFor(() => {
      expect(screen.getByText(/no failure labels recorded/i)).toBeInTheDocument()
    })
  })

  it('shows Run Trends empty state when time_series is empty', async () => {
    dashboardSummary.mockResolvedValue(minimalDashboard())
    dashboardAnalytics.mockResolvedValue(minimalAnalytics())

    render(<DashboardPanel pipelineConfigIds={[]} />)

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Run Trends', level: 2 })).toBeInTheDocument()
    })
    expect(screen.getByText(/no daily trend rows yet/i)).toBeInTheDocument()
  })

  it('shows Run Trends table from time_series', async () => {
    dashboardSummary.mockResolvedValue(minimalDashboard())
    dashboardAnalytics.mockResolvedValue({
      ...minimalAnalytics(),
      time_series: [
        {
          date: '2026-03-21',
          runs: 5,
          completed: 4,
          failed: 1,
          avg_total_latency_ms: 120.5,
          avg_cost_usd: null,
          failure_count: 2,
        },
      ],
    })

    render(<DashboardPanel pipelineConfigIds={[]} />)

    await waitFor(() => {
      expect(screen.getByRole('columnheader', { name: 'Date' })).toBeInTheDocument()
    })
    expect(screen.getByTestId('dashboard-trends-chart')).toBeInTheDocument()
    expect(screen.getByRole('cell', { name: '2026-03-21' })).toBeInTheDocument()
    expect(screen.getByRole('cell', { name: '5' })).toBeInTheDocument()
    expect(screen.getByRole('cell', { name: '4' })).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: 'Failed' })).toBeInTheDocument()
    expect(screen.getByRole('cell', { name: '121 ms' })).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: /avg cost/i })).toBeInTheDocument()
  })

  it('shows formatted cost in Run Trends when avg_cost_usd is present', async () => {
    dashboardSummary.mockResolvedValue(minimalDashboard())
    dashboardAnalytics.mockResolvedValue({
      ...minimalAnalytics(),
      time_series: [
        {
          date: '2026-03-20',
          runs: 3,
          completed: 3,
          failed: 0,
          avg_total_latency_ms: 80,
          avg_cost_usd: 0.004512,
          failure_count: 0,
        },
      ],
    })

    render(<DashboardPanel pipelineConfigIds={[]} />)

    await waitFor(() => {
      expect(screen.getByRole('cell', { name: '$0.004512' })).toBeInTheDocument()
    })
  })

  it('renders failure breakdown visual bars when failures exist', async () => {
    dashboardSummary.mockResolvedValue(minimalDashboard())
    dashboardAnalytics.mockResolvedValue({
      ...minimalAnalytics(),
      failure_analysis: {
        overall_counts: { UNKNOWN: 2, RETRIEVAL_MISS: 3 },
        overall_percentages: { UNKNOWN: 40, RETRIEVAL_MISS: 60 },
        by_config: [],
        recent_failed_runs: [],
      },
    })

    render(<DashboardPanel pipelineConfigIds={[]} />)

    await waitFor(() => {
      expect(screen.getByTestId('failure-overall-bars')).toBeInTheDocument()
    })
  })

  it('shows Config Insights empty state when config_insights is empty', async () => {
    dashboardSummary.mockResolvedValue(minimalDashboard())
    dashboardAnalytics.mockResolvedValue(minimalAnalytics())

    render(<DashboardPanel pipelineConfigIds={[]} />)

    await waitFor(() => {
      expect(screen.getByTestId('config-insights')).toBeInTheDocument()
    })
    expect(screen.getByText(/no config insights yet/i)).toBeInTheDocument()
  })

  it('renders Config Insights badges and sorted table', async () => {
    dashboardSummary.mockResolvedValue(minimalDashboard())
    dashboardAnalytics.mockResolvedValue({
      ...minimalAnalytics(),
      config_insights: [
        {
          pipeline_config_id: 1,
          pipeline_config_name: 'Busy slow',
          traced_runs: 8,
          completed_runs: 7,
          failed_runs: 1,
          avg_total_latency_ms: 400,
          min_total_latency_ms: 100,
          max_total_latency_ms: 500,
          avg_cost_usd: 0.02,
          total_cost_usd: 0.16,
          avg_retrieval_relevance: 0.55,
          avg_context_coverage: 0.6,
          avg_completeness: 0.62,
          avg_faithfulness: 0.58,
          latest_run_at: '2026-03-20T12:00:00.000Z',
          top_failure_type: 'UNKNOWN',
        },
        {
          pipeline_config_id: 2,
          pipeline_config_name: 'Fast quality',
          traced_runs: 3,
          completed_runs: 3,
          failed_runs: 0,
          avg_total_latency_ms: 90,
          min_total_latency_ms: 80,
          max_total_latency_ms: 120,
          avg_cost_usd: 0.005,
          total_cost_usd: 0.015,
          avg_retrieval_relevance: 0.92,
          avg_context_coverage: 0.88,
          avg_completeness: 0.9,
          avg_faithfulness: 0.87,
          latest_run_at: '2026-03-19T10:00:00.000Z',
          top_failure_type: null,
        },
      ],
    })

    render(<DashboardPanel pipelineConfigIds={[]} />)

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Config Insights', level: 2 })).toBeInTheDocument()
    })

    const section = screen.getByTestId('config-insights')
    expect(section.textContent).toMatch(/Fastest/i)
    expect(section.textContent).toMatch(/Most used/i)

    const table = within(section).getByRole('table')
    expect(within(table).getByText('Fast quality')).toBeInTheDocument()
    const rows = within(table).getAllByRole('row')
    // header + Busy slow (8 traced) first + Fast quality second
    expect(rows[1]).toHaveTextContent('Busy slow')
    expect(rows[2]).toHaveTextContent('Fast quality')
    expect(rows[1].className).toMatch(/cl-config-insight-row--attention/)
    expect(rows[2].className).toMatch(/cl-config-insight-row--highlight/)
  })

  it('renders export actions when loaded and triggers download helpers', async () => {
    const dl = vi.spyOn(exportDownload, 'triggerBrowserDownload').mockImplementation(() => {})
    dashboardSummary.mockResolvedValue(minimalDashboard())
    dashboardAnalytics.mockResolvedValue(minimalAnalytics())
    configComparison.mockResolvedValue(emptyConfigComparisonBoth())

    render(<DashboardPanel pipelineConfigIds={[]} />)

    await waitFor(() => {
      expect(screen.getByTestId('dashboard-export-json')).not.toBeDisabled()
    })
    expect(screen.getByTestId('dashboard-export-csv')).not.toBeDisabled()

    fireEvent.click(screen.getByTestId('dashboard-export-json'))
    expect(dl).toHaveBeenCalledWith(
      'contextlens-dashboard.json',
      expect.stringMatching(/"total_runs"\s*:\s*1/),
      'application/json',
    )

    fireEvent.click(screen.getByTestId('dashboard-export-csv'))
    expect(dl).toHaveBeenCalledWith(
      'contextlens-dashboard.csv',
      expect.stringContaining('section,recent_runs'),
      'text/csv;charset=utf-8',
    )

    dl.mockRestore()
  })

  it('renders LLM score spread (best/worst config + delta %) in comparison snapshot', async () => {
    dashboardSummary.mockResolvedValue(minimalDashboard())
    dashboardAnalytics.mockResolvedValue(minimalAnalytics())
    configComparison.mockResolvedValue(
      emptyConfigComparisonBoth({
        pipeline_config_ids: [1, 2],
        buckets: {
          heuristic: [minimalCompareRow({ pipeline_config_id: 1, traced_runs: 1 })],
          llm: [minimalCompareRow({ pipeline_config_id: 2, traced_runs: 2, avg_faithfulness: 0.9 })],
        },
        score_comparison_buckets: {
          heuristic: nullScoreSummary(),
          llm: {
            best_config_faithfulness: 2,
            worst_config_faithfulness: 1,
            faithfulness_delta_pct: 25.5,
            best_config_completeness: 3,
            worst_config_completeness: 1,
            completeness_delta_pct: 10,
          },
        },
      }),
    )

    render(<DashboardPanel pipelineConfigIds={[1, 2]} />)

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /Pipeline configs — llm/i })).toBeInTheDocument()
    })
    const llmHeading = screen.getByRole('heading', { name: /Pipeline configs — llm/i })
    const llmSection = llmHeading.closest('.cl-dash-bucket')
    expect(llmSection).toBeTruthy()
    expect(within(llmSection! as HTMLElement).getByText(/Faithfulness — best \/ worst config/i)).toBeInTheDocument()
    const blob = llmSection!.textContent ?? ''
    expect(blob).toMatch(/2\s*\/\s*1/)
    expect(blob).toContain('25.5%')
    expect(blob).toMatch(/Completeness — best \/ worst config[\s\S]*3\s*\/\s*1/)
    expect(blob).toContain('10.0%')
  })
})
