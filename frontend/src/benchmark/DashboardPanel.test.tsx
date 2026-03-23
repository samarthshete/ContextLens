/** @vitest-environment jsdom */
import '@testing-library/jest-dom/vitest'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { ConfigComparisonMetrics, DashboardSummaryResponse, Dataset } from '../api/types'
import { emptyConfigComparisonBoth, nullScoreSummary } from './configComparisonMock'
import { DashboardPanel, pickLatestDatasetId } from './DashboardPanel'
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

const TEST_DATASETS: Dataset[] = [
  {
    id: 1,
    name: 'Test',
    description: null,
    created_at: '2026-01-01T00:00:00Z',
  },
]

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
    config_insights: { heuristic: [], llm: [] },
  }
}

function minimalCompareRow(over: Partial<ConfigComparisonMetrics> = {}): ConfigComparisonMetrics {
  return {
    pipeline_config_id: 1,
    traced_runs: 0,
    unique_query_count: 0,
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

function buildRepeatedSamplingNote(totalRuns: number, uniqueQueries: number): string {
  return `${totalRuns} runs across ${uniqueQueries} unique queries (repeated sampling; results are directional, not broad generalization)`
}

function minimalDashboard(over: Partial<DashboardSummaryResponse> = {}): DashboardSummaryResponse {
  const merged: DashboardSummaryResponse = {
    total_runs: 1,
    repeated_sampling_note: '',
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
      total_latency_p50_ms: 15,
      end_to_end_run_latency_avg_sec: 0.015,
      end_to_end_run_latency_p50_sec: 0.015,
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
    model_failures: 0,
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
  if (over.repeated_sampling_note === undefined) {
    merged.repeated_sampling_note = buildRepeatedSamplingNote(merged.total_runs, merged.scale.total_queries)
  }
  return merged
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
        evaluator_counts: { heuristic_runs: 0, llm_runs: 10, runs_without_evaluation: 0 },
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
    render(
      <DashboardPanel
        pipelineConfigIds={[1]}
        datasets={TEST_DATASETS}
        registryLoading={false}
      />,
    )
    await waitFor(() => expect(screen.queryByText(/Loading dashboard/)).not.toBeInTheDocument())
    expect(screen.getByText(/Average per LLM run \(measured cost only\)/i)).toBeInTheDocument()
    expect(screen.getByText(/Average per full RAG run/i)).toBeInTheDocument()
    expect(screen.getByText(/\(2 runs with non-null cost/i)).toBeInTheDocument()
  })

  it('renders system scale metrics from dashboard summary', async () => {
    dashboardSummary.mockResolvedValue(minimalDashboard())
    dashboardAnalytics.mockResolvedValue(minimalAnalytics())
    configComparison.mockResolvedValue(emptyConfigComparisonBoth({ pipeline_config_ids: [1] }))
    render(
      <DashboardPanel
        pipelineConfigIds={[1]}
        datasets={TEST_DATASETS}
        registryLoading={false}
      />,
    )
    await waitFor(() => expect(screen.queryByText(/Loading dashboard/)).not.toBeInTheDocument())
    const scale = screen.getByTestId('dashboard-system-scale')
    expect(within(scale).getByText('Benchmark datasets')).toBeInTheDocument()
    expect(within(scale).getByText('3')).toBeInTheDocument() // total_queries
    expect(within(scale).getByText('8')).toBeInTheDocument() // chunks_indexed
  })

  it('renders retrieval median, P95, and mean in that order from dashboard summary', async () => {
    dashboardSummary.mockResolvedValue(
      minimalDashboard({
        latency: {
          avg_retrieval_latency_ms: 42,
          retrieval_latency_p50_ms: 40,
          retrieval_latency_p95_ms: 88,
          avg_generation_latency_ms: null,
          avg_evaluation_latency_ms: 5,
          avg_total_latency_ms: 120,
          total_latency_p50_ms: 100,
          end_to_end_run_latency_avg_sec: 0.12,
          end_to_end_run_latency_p50_sec: 0.1,
          end_to_end_run_latency_p95_sec: 0.12,
        },
      }),
    )
    dashboardAnalytics.mockResolvedValue(minimalAnalytics())
    configComparison.mockResolvedValue(emptyConfigComparisonBoth({ pipeline_config_ids: [1] }))
    render(
      <DashboardPanel
        pipelineConfigIds={[1]}
        datasets={TEST_DATASETS}
        registryLoading={false}
      />,
    )
    await waitFor(() => expect(screen.queryByText(/Loading dashboard/)).not.toBeInTheDocument())
    const retrieval = screen.getByTestId('dashboard-retrieval-latency')
    expect(within(retrieval).getByText('42 ms')).toBeInTheDocument()
    expect(within(retrieval).getByText('40 ms')).toBeInTheDocument()
    expect(within(retrieval).getByText('88 ms')).toBeInTheDocument()
    const rItems = within(retrieval).getAllByRole('listitem')
    expect(rItems[0]).toHaveTextContent(/Median \(P50\)/)
    expect(rItems[1]).toHaveTextContent(/P95/)
    expect(rItems[2]).toHaveTextContent(/Mean/)
    expect(screen.getByTestId('dashboard-latency-median-note')).toHaveTextContent(
      'Median is more representative than average when cold-start outliers are present.',
    )
  })

  it('shows model quality insight when model_failures > 0', async () => {
    dashboardSummary.mockResolvedValue(
      minimalDashboard({
        total_runs: 10,
        model_failures: 3,
        status_counts: { completed: 10, failed: 0, in_progress: 0 },
      }),
    )
    dashboardAnalytics.mockResolvedValue(minimalAnalytics())
    configComparison.mockResolvedValue(emptyConfigComparisonBoth({ pipeline_config_ids: [1] }))
    render(
      <DashboardPanel
        pipelineConfigIds={[1]}
        datasets={TEST_DATASETS}
        registryLoading={false}
      />,
    )
    await waitFor(() => expect(screen.getByTestId('dashboard-model-quality-insight')).toBeInTheDocument())
    expect(screen.getByTestId('dashboard-model-quality-insight')).toHaveTextContent(/30\.0%/)
    expect(screen.getByTestId('dashboard-model-quality-insight')).toHaveTextContent(/0 system failures/i)
  })

  it('shows per-phase insufficient distribution copy when samples < 5 (no global gate)', async () => {
    dashboardSummary.mockResolvedValue(minimalDashboard())
    dashboardAnalytics.mockResolvedValue({
      ...minimalAnalytics(),
      latency_distribution: {
        retrieval: { count: 2, min_ms: 1, max_ms: 50, avg_ms: 20, median_ms: 18, p95_ms: 45 },
        generation: { count: 0, min_ms: null, max_ms: null, avg_ms: null, median_ms: null, p95_ms: null },
        evaluation: { count: 2, min_ms: 2, max_ms: 30, avg_ms: 10, median_ms: 9, p95_ms: 28 },
        total: { count: 5, min_ms: 20, max_ms: 200, avg_ms: 100, median_ms: 95, p95_ms: 180 },
      },
    })
    configComparison.mockResolvedValue(emptyConfigComparisonBoth({ pipeline_config_ids: [1] }))
    render(
      <DashboardPanel
        pipelineConfigIds={[1]}
        datasets={TEST_DATASETS}
        registryLoading={false}
      />,
    )
    await waitFor(() => expect(screen.getByTestId('latency-phase-insufficient-retrieval')).toBeInTheDocument())
    expect(screen.getByTestId('latency-phase-insufficient-retrieval')).toHaveTextContent(
      'Insufficient samples for distribution (2 runs)',
    )
    expect(screen.getByTestId('latency-phase-insufficient-evaluation')).toBeInTheDocument()
    expect(screen.getByTestId('latency-phase-empty-generation')).toBeInTheDocument()
    expect(screen.queryByTestId('latency-distribution-insufficient')).not.toBeInTheDocument()
    expect(screen.getByTestId('latency-median-vs-avg-note')).toBeInTheDocument()
  })

  it('renders end-to-end median, P95, then means from dashboard summary', async () => {
    dashboardSummary.mockResolvedValue(
      minimalDashboard({
        latency: {
          avg_retrieval_latency_ms: 10,
          retrieval_latency_p50_ms: 10,
          retrieval_latency_p95_ms: 10,
          avg_generation_latency_ms: null,
          avg_evaluation_latency_ms: 5,
          avg_total_latency_ms: 1500,
          total_latency_p50_ms: 1200,
          end_to_end_run_latency_avg_sec: 1.5,
          end_to_end_run_latency_p50_sec: 1.2,
          end_to_end_run_latency_p95_sec: 2.25,
        },
      }),
    )
    dashboardAnalytics.mockResolvedValue(minimalAnalytics())
    configComparison.mockResolvedValue(emptyConfigComparisonBoth({ pipeline_config_ids: [1] }))
    render(
      <DashboardPanel
        pipelineConfigIds={[1]}
        datasets={TEST_DATASETS}
        registryLoading={false}
      />,
    )
    await waitFor(() => expect(screen.queryByText(/Loading dashboard/)).not.toBeInTheDocument())
    const block = screen.getByTestId('dashboard-end-to-end-latency')
    expect(within(block).getByText(/1200 ms/)).toBeInTheDocument()
    expect(within(block).getByText(/1\.200 s/)).toBeInTheDocument()
    expect(within(block).getByText(/2250 ms/)).toBeInTheDocument()
    expect(within(block).getByText(/2\.250 s/)).toBeInTheDocument()
    expect(within(block).getByText(/1500 ms/)).toBeInTheDocument()
    const e2eItems = within(block).getAllByRole('listitem')
    expect(e2eItems[0]).toHaveTextContent(/Median \(P50\)/)
    expect(e2eItems[1]).toHaveTextContent(/P95/)
    expect(e2eItems[2]).toHaveTextContent(/Mean \(ms\)/)
    expect(e2eItems[3]).toHaveTextContent(/Mean \(s\)/)
  })

  it('shows loading then summary cards from API', async () => {
    dashboardSummary.mockResolvedValue(minimalDashboard())
    dashboardAnalytics.mockResolvedValue({
      ...minimalAnalytics(),
      latency_distribution: {
        retrieval: { count: 5, min_ms: 1, max_ms: 50, avg_ms: 20, median_ms: 18, p95_ms: 45 },
        generation: { count: 0, min_ms: null, max_ms: null, avg_ms: null, median_ms: null, p95_ms: null },
        evaluation: { count: 5, min_ms: 2, max_ms: 30, avg_ms: 10, median_ms: 9, p95_ms: 28 },
        total: { count: 5, min_ms: 20, max_ms: 200, avg_ms: 100, median_ms: 95, p95_ms: 180 },
      },
    })
    configComparison.mockResolvedValue(emptyConfigComparisonBoth({ pipeline_config_ids: [1] }))

    render(
      <DashboardPanel
        pipelineConfigIds={[1]}
        datasets={TEST_DATASETS}
        registryLoading={false}
      />,
    )

    expect(screen.getByText(/loading dashboard/i)).toBeInTheDocument()

    await waitFor(() => {
      expect(screen.getByText('Total runs')).toBeInTheDocument()
    })
    expect(dashboardSummary).toHaveBeenCalledWith({ datasetId: 1 })
    expect(dashboardAnalytics).toHaveBeenCalledWith({ datasetId: 1 })
    expect(configComparison).toHaveBeenCalledWith([1], { evaluatorType: 'both', datasetId: 1 })
    const totalCard = screen.getByText('Total runs').closest('.cl-dash-stat')
    expect(totalCard).toHaveTextContent('1')
    expect(screen.getByRole('heading', { name: 'Latency', level: 2 })).toBeInTheDocument()
    expect(screen.getByTestId('dashboard-latency-median-note')).toHaveTextContent(
      /Median is more representative than average when cold-start outliers are present/i,
    )
    expect(screen.getByTestId('latency-median-vs-avg-note')).toHaveTextContent(
      /Median is more representative than average when cold-start outliers are present/i,
    )
    expect(screen.getByTestId('dashboard-repeated-sampling-note')).toHaveTextContent(
      /repeated sampling/i,
    )
    expect(screen.getByText(/recent runs/i)).toBeInTheDocument()
    expect(screen.getByRole('cell', { name: '7' })).toBeInTheDocument()
  })

  it('shows registry loading state before datasets are ready', () => {
    render(
      <DashboardPanel pipelineConfigIds={[]} datasets={[]} registryLoading={true} />,
    )
    expect(screen.getByTestId('dashboard-registry-loading')).toBeInTheDocument()
    expect(dashboardSummary).not.toHaveBeenCalled()
  })

  it('shows select dataset message when registry has no datasets', () => {
    render(
      <DashboardPanel pipelineConfigIds={[]} datasets={[]} registryLoading={false} />,
    )
    expect(screen.getByTestId('dashboard-select-dataset-msg')).toBeInTheDocument()
    expect(dashboardSummary).not.toHaveBeenCalled()
  })

  it('shows error when dashboardSummary fails', async () => {
    dashboardSummary.mockRejectedValue(new Error('network down'))
    dashboardAnalytics.mockResolvedValue(minimalAnalytics())

    render(
      <DashboardPanel pipelineConfigIds={[]} datasets={TEST_DATASETS} registryLoading={false} />,
    )

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent(/network down/i)
    })
    expect(screen.getByTestId('dashboard-export-json')).toBeDisabled()
    expect(screen.getByTestId('dashboard-export-csv')).toBeDisabled()
  })

  it('shows empty failure section copy', async () => {
    dashboardSummary.mockResolvedValue(minimalDashboard({ failure_type_counts: {} }))
    dashboardAnalytics.mockResolvedValue(minimalAnalytics())

    render(
      <DashboardPanel pipelineConfigIds={[]} datasets={TEST_DATASETS} registryLoading={false} />,
    )

    await waitFor(() => {
      expect(screen.getByText(/no failure labels recorded/i)).toBeInTheDocument()
    })
  })

  it('shows Run Trends empty state when time_series is empty', async () => {
    dashboardSummary.mockResolvedValue(minimalDashboard())
    dashboardAnalytics.mockResolvedValue(minimalAnalytics())

    render(
      <DashboardPanel pipelineConfigIds={[]} datasets={TEST_DATASETS} registryLoading={false} />,
    )

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

    render(
      <DashboardPanel pipelineConfigIds={[]} datasets={TEST_DATASETS} registryLoading={false} />,
    )

    await waitFor(() => {
      expect(screen.getByRole('columnheader', { name: 'Date' })).toBeInTheDocument()
    })
    expect(screen.getByTestId('dashboard-trends-chart')).toBeInTheDocument()
    expect(screen.getByTestId('dashboard-trends-dataset-scope')).toHaveTextContent(/Test \(#1\)/)
    expect(screen.getByRole('cell', { name: '2026-03-21' })).toBeInTheDocument()
    expect(screen.getByRole('cell', { name: '5' })).toBeInTheDocument()
    expect(screen.getByRole('cell', { name: '4' })).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: 'System failures' })).toBeInTheDocument()
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

    render(
      <DashboardPanel pipelineConfigIds={[]} datasets={TEST_DATASETS} registryLoading={false} />,
    )

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

    render(
      <DashboardPanel pipelineConfigIds={[]} datasets={TEST_DATASETS} registryLoading={false} />,
    )

    await waitFor(() => {
      expect(screen.getByTestId('failure-overall-bars')).toBeInTheDocument()
    })
  })

  it('shows Config Insights empty state when config_insights is empty', async () => {
    dashboardSummary.mockResolvedValue(minimalDashboard())
    dashboardAnalytics.mockResolvedValue(minimalAnalytics())

    render(
      <DashboardPanel pipelineConfigIds={[]} datasets={TEST_DATASETS} registryLoading={false} />,
    )

    await waitFor(() => {
      expect(screen.getByTestId('config-insights')).toBeInTheDocument()
    })
    expect(screen.getByText(/no config insights yet/i)).toBeInTheDocument()
  })

  it('renders system vs model failure cards and helper copy', async () => {
    dashboardSummary.mockResolvedValue(
      minimalDashboard({
        status_counts: { completed: 5, failed: 2, in_progress: 0 },
        model_failures: 7,
      }),
    )
    dashboardAnalytics.mockResolvedValue(minimalAnalytics())
    configComparison.mockResolvedValue(emptyConfigComparisonBoth({ pipeline_config_ids: [1] }))
    render(
      <DashboardPanel
        pipelineConfigIds={[1]}
        datasets={TEST_DATASETS}
        registryLoading={false}
      />,
    )
    await waitFor(() => expect(screen.queryByText(/Loading dashboard/)).not.toBeInTheDocument())
    expect(screen.getByTestId('dashboard-system-failures-count')).toHaveTextContent('2')
    expect(screen.getByTestId('dashboard-model-failures-count')).toHaveTextContent('7')
    const runCounts = screen.getByRole('region', { name: 'Run counts' })
    expect(within(runCounts).getByText('System failures')).toBeInTheDocument()
    expect(within(runCounts).getByText('Model failures')).toBeInTheDocument()
    expect(screen.getByText(/pipeline did not complete successfully/i)).toBeInTheDocument()
    expect(screen.getByText(/evaluation rows with a non/i)).toBeInTheDocument()
  })

  it('hides LLM insights table when llm_runs < 3 (sparse gate only)', async () => {
    dashboardSummary.mockResolvedValue(
      minimalDashboard({
        evaluator_counts: { heuristic_runs: 0, llm_runs: 2, runs_without_evaluation: 0 },
      }),
    )
    dashboardAnalytics.mockResolvedValue({
      ...minimalAnalytics(),
      config_insights: {
        heuristic: [],
        llm: [
          {
            pipeline_config_id: 1,
            pipeline_config_name: 'cfg',
            traced_runs: 2,
            completed_runs: 2,
            failed_runs: 0,
            avg_total_latency_ms: 100,
            min_total_latency_ms: 90,
            max_total_latency_ms: 110,
            avg_cost_usd: 0.01,
            total_cost_usd: 0.02,
            avg_retrieval_relevance: 0.5,
            avg_context_coverage: 0.5,
            avg_completeness: 0.5,
            avg_faithfulness: 0.5,
            latest_run_at: '2026-03-20T12:00:00.000Z',
            top_failure_type: null,
          },
        ],
      },
    })
    render(
      <DashboardPanel pipelineConfigIds={[]} datasets={TEST_DATASETS} registryLoading={false} />,
    )
    await waitFor(() => expect(screen.getByTestId('config-insights-tradeoff')).toBeInTheDocument())
    expect(screen.getByTestId('config-insights-tradeoff')).toHaveTextContent(/retrieval relevance/i)
    expect(screen.getByTestId('dashboard-llm-insights-sparse-gate')).toHaveTextContent(
      /Sparse sample \(2 runs\) — not reliable/i,
    )
    expect(screen.queryByTestId('dashboard-llm-evidence-limited')).not.toBeInTheDocument()
    expect(within(screen.getByTestId('config-insights-llm')).queryByRole('table')).not.toBeInTheDocument()
  })

  it('shows LLM illustrative warning when 3 ≤ llm_runs < 10', async () => {
    dashboardSummary.mockResolvedValue(
      minimalDashboard({
        evaluator_counts: { heuristic_runs: 0, llm_runs: 5, runs_without_evaluation: 0 },
      }),
    )
    dashboardAnalytics.mockResolvedValue({
      ...minimalAnalytics(),
      config_insights: {
        heuristic: [],
        llm: [
          {
            pipeline_config_id: 1,
            pipeline_config_name: 'cfg',
            traced_runs: 5,
            completed_runs: 5,
            failed_runs: 0,
            avg_total_latency_ms: 100,
            min_total_latency_ms: 90,
            max_total_latency_ms: 110,
            avg_cost_usd: 0.01,
            total_cost_usd: 0.05,
            avg_retrieval_relevance: 0.5,
            avg_context_coverage: 0.5,
            avg_completeness: 0.5,
            avg_faithfulness: 0.5,
            latest_run_at: '2026-03-20T12:00:00.000Z',
            top_failure_type: null,
          },
        ],
      },
    })
    render(
      <DashboardPanel pipelineConfigIds={[]} datasets={TEST_DATASETS} registryLoading={false} />,
    )
    await waitFor(() => expect(screen.getByTestId('dashboard-llm-evidence-limited')).toBeInTheDocument())
    expect(screen.getByTestId('dashboard-llm-evidence-limited')).toHaveTextContent(
      /LLM evidence is limited; treat this as illustrative, not conclusive/i,
    )
  })

  it('renders Config Insights badges and sorted table', async () => {
    dashboardSummary.mockResolvedValue(
      minimalDashboard({
        evaluator_counts: { heuristic_runs: 1, llm_runs: 12, runs_without_evaluation: 0 },
      }),
    )
    dashboardAnalytics.mockResolvedValue({
      ...minimalAnalytics(),
      config_insights: {
        heuristic: [],
        llm: [
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
      },
    })

    render(
      <DashboardPanel pipelineConfigIds={[]} datasets={TEST_DATASETS} registryLoading={false} />,
    )

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Config insights', level: 2 })).toBeInTheDocument()
    })

    const section = screen.getByTestId('config-insights-llm')
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

    render(
      <DashboardPanel pipelineConfigIds={[]} datasets={TEST_DATASETS} registryLoading={false} />,
    )

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
    dashboardSummary.mockResolvedValue(
      minimalDashboard({ evaluator_counts: { heuristic_runs: 1, llm_runs: 10, runs_without_evaluation: 0 } }),
    )
    dashboardAnalytics.mockResolvedValue(minimalAnalytics())
    configComparison.mockResolvedValue(
      emptyConfigComparisonBoth({
        pipeline_config_ids: [1, 2],
        buckets: {
          heuristic: [minimalCompareRow({ pipeline_config_id: 1, traced_runs: 1 })],
          llm: [
            minimalCompareRow({
              pipeline_config_id: 1,
              traced_runs: 1,
              avg_faithfulness: 0.4,
              avg_completeness: 0.5,
            }),
            minimalCompareRow({
              pipeline_config_id: 2,
              traced_runs: 2,
              avg_faithfulness: 0.502,
              avg_completeness: 0.505,
            }),
          ],
        },
        score_comparison_buckets: {
          heuristic: nullScoreSummary(),
          llm: {
            best_config_faithfulness: 2,
            worst_config_faithfulness: 1,
            faithfulness_delta_pct: 25.5,
            best_config_completeness: 2,
            worst_config_completeness: 1,
            completeness_delta_pct: 1.0,
          },
        },
      }),
    )

    render(
      <DashboardPanel
        pipelineConfigIds={[1, 2]}
        datasets={TEST_DATASETS}
        registryLoading={false}
      />,
    )

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
    expect(blob).toMatch(/Completeness — best \/ worst config[\s\S]*2\s*\/\s*1/)
    expect(blob).toContain('1.0%')
    expect(within(llmSection! as HTMLElement).getByTestId('completeness-small-delta-caveat')).toHaveTextContent(
      /Completeness difference is small on this dataset/i,
    )
  })

  it('shows comparison reliability banner with LOW confidence for 6 unique queries', async () => {
    dashboardSummary.mockResolvedValue(
      minimalDashboard({
        evaluator_counts: { heuristic_runs: 48, llm_runs: 5, runs_without_evaluation: 0 },
      }),
    )
    dashboardAnalytics.mockResolvedValue(minimalAnalytics())
    configComparison.mockResolvedValue(
      emptyConfigComparisonBoth({
        pipeline_config_ids: [1, 2],
        comparison_confidence: 'LOW',
        comparison_statistically_reliable: false,
        effective_sample_size: 6,
        unique_queries_compared: 6,
        min_traced_runs_across_configs: 26,
        buckets: {
          heuristic: [
            minimalCompareRow({ pipeline_config_id: 1, traced_runs: 27, unique_query_count: 6 }),
            minimalCompareRow({ pipeline_config_id: 2, traced_runs: 26, unique_query_count: 6 }),
          ],
          llm: [],
        },
      }),
    )
    render(
      <DashboardPanel
        pipelineConfigIds={[1, 2]}
        datasets={TEST_DATASETS}
        registryLoading={false}
      />,
    )
    await waitFor(() => expect(screen.getByTestId('compare-reliability-banner')).toBeInTheDocument())
    expect(screen.getByTestId('compare-confidence-badge')).toHaveTextContent('Confidence: LOW')
    expect(screen.getByTestId('compare-not-reliable-badge')).toHaveTextContent('Not statistically reliable')
    expect(screen.getByTestId('compare-effective-sample')).toHaveTextContent(/Effective sample size: 6/)
  })

  it('shows zero-runs warning when a config has traced_runs=0', async () => {
    dashboardSummary.mockResolvedValue(minimalDashboard())
    dashboardAnalytics.mockResolvedValue(minimalAnalytics())
    configComparison.mockResolvedValue(
      emptyConfigComparisonBoth({
        pipeline_config_ids: [1, 2],
        buckets: {
          heuristic: [
            minimalCompareRow({ pipeline_config_id: 1, traced_runs: 5, unique_query_count: 3 }),
            minimalCompareRow({ pipeline_config_id: 2, traced_runs: 0, unique_query_count: 0 }),
          ],
          llm: [],
        },
      }),
    )
    render(
      <DashboardPanel
        pipelineConfigIds={[1, 2]}
        datasets={TEST_DATASETS}
        registryLoading={false}
      />,
    )
    await waitFor(() => expect(screen.getByTestId('compare-zero-runs-warning')).toBeInTheDocument())
    expect(screen.getByTestId('compare-zero-runs-warning')).toHaveTextContent(
      /One or more configs have no traced runs/,
    )
  })

  it('shows LLM eval insight with both success and retrieval failures', async () => {
    dashboardSummary.mockResolvedValue(
      minimalDashboard({
        total_runs: 53,
        model_failures: 37,
        evaluator_counts: { heuristic_runs: 48, llm_runs: 5, runs_without_evaluation: 0 },
        failure_type_counts: {
          NO_FAILURE: 16,
          RETRIEVAL_MISS: 3,
          RETRIEVAL_PARTIAL: 25,
          ANSWER_INCOMPLETE: 9,
        },
      }),
    )
    dashboardAnalytics.mockResolvedValue(minimalAnalytics())
    configComparison.mockResolvedValue(emptyConfigComparisonBoth({ pipeline_config_ids: [] }))
    render(
      <DashboardPanel pipelineConfigIds={[]} datasets={TEST_DATASETS} registryLoading={false} />,
    )
    await waitFor(() => expect(screen.getByTestId('dashboard-llm-eval-insight')).toBeInTheDocument())
    expect(screen.getByTestId('dashboard-llm-eval-insight-text')).toHaveTextContent(
      /LLM evaluation captures both successful grounded responses and retrieval failures/,
    )
    expect(screen.getByTestId('dashboard-llm-eval-limited')).toHaveTextContent(
      /Limited evidence \(5 runs\) — directional only/,
    )
  })

  it('shows sparse sample warning for LLM insight when llm_runs < 3', async () => {
    dashboardSummary.mockResolvedValue(
      minimalDashboard({
        evaluator_counts: { heuristic_runs: 10, llm_runs: 1, runs_without_evaluation: 0 },
        failure_type_counts: { NO_FAILURE: 5, RETRIEVAL_MISS: 2 },
        model_failures: 2,
        total_runs: 7,
      }),
    )
    dashboardAnalytics.mockResolvedValue(minimalAnalytics())
    render(
      <DashboardPanel pipelineConfigIds={[]} datasets={TEST_DATASETS} registryLoading={false} />,
    )
    await waitFor(() => expect(screen.getByTestId('dashboard-llm-eval-insight')).toBeInTheDocument())
    expect(screen.getByTestId('dashboard-llm-eval-insight')).toHaveTextContent(
      /Sparse sample \(1 run\) — not reliable/,
    )
  })

  it('shows repeated sampling context in comparison section', async () => {
    dashboardSummary.mockResolvedValue(
      minimalDashboard({
        evaluator_counts: { heuristic_runs: 48, llm_runs: 5, runs_without_evaluation: 0 },
      }),
    )
    dashboardAnalytics.mockResolvedValue(minimalAnalytics())
    configComparison.mockResolvedValue(
      emptyConfigComparisonBoth({
        pipeline_config_ids: [1, 2],
        buckets: {
          heuristic: [
            minimalCompareRow({ pipeline_config_id: 1, traced_runs: 27, unique_query_count: 6 }),
            minimalCompareRow({ pipeline_config_id: 2, traced_runs: 26, unique_query_count: 6 }),
          ],
          llm: [],
        },
      }),
    )
    render(
      <DashboardPanel
        pipelineConfigIds={[1, 2]}
        datasets={TEST_DATASETS}
        registryLoading={false}
      />,
    )
    await waitFor(() => expect(screen.getByTestId('compare-repeated-sampling')).toBeInTheDocument())
    expect(screen.getByTestId('compare-repeated-sampling')).toHaveTextContent(
      /Runs: 53 across 6 unique queries \(repeated sampling\)/,
    )
  })
})

describe('pickLatestDatasetId', () => {
  it('returns null for empty list', () => {
    expect(pickLatestDatasetId([])).toBeNull()
  })

  it('picks newest by created_at', () => {
    const ds: Dataset[] = [
      { id: 10, name: 'old', description: null, created_at: '2025-01-01T00:00:00Z' },
      { id: 22, name: 'new', description: null, created_at: '2026-06-01T00:00:00Z' },
    ]
    expect(pickLatestDatasetId(ds)).toBe(22)
  })
})
