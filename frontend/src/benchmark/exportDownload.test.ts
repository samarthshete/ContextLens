/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type {
  DashboardAnalyticsResponse,
  DashboardSummaryResponse,
  RunDetail,
} from '../api/types'
import {
  buildDashboardExportBundle,
  buildDashboardExportCsv,
  csvEscapeCell,
  dashboardExportCsvFilename,
  dashboardExportJsonFilename,
  joinCsvRow,
  runTraceExportFilename,
  serializeDashboardExportJson,
  serializeRunTraceJson,
  triggerBrowserDownload,
} from './exportDownload'

function minimalRun(over: Partial<RunDetail> = {}): RunDetail {
  return {
    run_id: 11,
    status: 'completed',
    created_at: '2026-01-02T00:00:00Z',
    retrieval_latency_ms: 1,
    generation_latency_ms: null,
    evaluation_latency_ms: 2,
    total_latency_ms: 3,
    evaluator_type: 'heuristic',
    query_case: {
      id: 1,
      dataset_id: 1,
      query_text: 'q',
      expected_answer: null,
    },
    pipeline_config: {
      id: 2,
      name: 'p',
      embedding_model: 'e',
      chunk_strategy: 'fixed',
      chunk_size: 256,
      chunk_overlap: 0,
      top_k: 5,
    },
    retrieval_hits: [],
    generation: null,
    evaluation: null,
    ...over,
  }
}

function tinySummary(): DashboardSummaryResponse {
  return {
    total_runs: 2,
    scale: {
      benchmark_datasets: 1,
      total_queries: 4,
      total_traced_runs: 2,
      configs_tested: 2,
      documents_processed: 1,
      chunks_indexed: 5,
    },
    status_counts: { completed: 2, failed: 0, in_progress: 0 },
    evaluator_counts: { heuristic_runs: 2, llm_runs: 0, runs_without_evaluation: 0 },
    latency: {
      avg_retrieval_latency_ms: 10,
      retrieval_latency_p50_ms: 9,
      retrieval_latency_p95_ms: 15,
      avg_generation_latency_ms: null,
      avg_evaluation_latency_ms: null,
      avg_total_latency_ms: 20,
      end_to_end_run_latency_avg_sec: 0.02,
      end_to_end_run_latency_p95_sec: 0.03,
    },
    cost: {
      total_cost_usd: null,
      avg_cost_usd: null,
      evaluation_rows_with_cost: 0,
      evaluation_rows_cost_not_available: 2,
      avg_cost_usd_per_llm_run: null,
      llm_runs_with_measured_cost: 0,
      avg_cost_usd_per_full_rag_run: null,
      full_rag_runs_with_measured_cost: 0,
    },
    failure_type_counts: { UNKNOWN: 1 },
    recent_runs: [
      {
        run_id: 5,
        status: 'completed',
        created_at: '2026-03-01T00:00:00Z',
        evaluator_type: 'heuristic',
        total_latency_ms: 20,
        cost_usd: null,
        failure_type: 'UNKNOWN',
      },
    ],
  }
}

function tinyAnalytics(): DashboardAnalyticsResponse {
  return {
    time_series: [
      {
        date: '2026-03-20',
        runs: 1,
        completed: 1,
        failed: 0,
        avg_total_latency_ms: 100,
        avg_cost_usd: null,
        failure_count: 0,
      },
    ],
    latency_distribution: {
      retrieval: { count: 1, min_ms: 1, max_ms: 9, avg_ms: 5, median_ms: 5, p95_ms: 9 },
      generation: { count: 0, min_ms: null, max_ms: null, avg_ms: null, median_ms: null, p95_ms: null },
      evaluation: { count: 1, min_ms: 2, max_ms: 8, avg_ms: 4, median_ms: 4, p95_ms: 8 },
      total: { count: 1, min_ms: 10, max_ms: 110, avg_ms: 100, median_ms: 100, p95_ms: 110 },
    },
    end_to_end_run_latency_avg_sec: 0.1,
    end_to_end_run_latency_p95_sec: 0.11,
    failure_analysis: {
      overall_counts: {},
      overall_percentages: {},
      by_config: [],
      recent_failed_runs: [],
    },
    config_insights: {
      heuristic: [],
      llm: [
        {
          pipeline_config_id: 9,
          pipeline_config_name: 'cfg"a',
          traced_runs: 3,
          completed_runs: 2,
          failed_runs: 1,
          avg_total_latency_ms: 50,
          min_total_latency_ms: 40,
          max_total_latency_ms: 60,
          avg_cost_usd: 0.01,
          total_cost_usd: 0.03,
          avg_retrieval_relevance: 0.5,
          avg_context_coverage: 0.6,
          avg_completeness: 0.7,
          avg_faithfulness: null,
          latest_run_at: '2026-03-20T00:00:00Z',
          top_failure_type: 'UNKNOWN',
        },
      ],
    },
  }
}

describe('exportDownload', () => {
  const origCreate = URL.createObjectURL?.bind(URL)
  const origRevoke = URL.revokeObjectURL?.bind(URL)

  beforeEach(() => {
    Object.defineProperty(URL, 'createObjectURL', {
      configurable: true,
      writable: true,
      value: vi.fn(() => 'blob:unit-test'),
    })
    Object.defineProperty(URL, 'revokeObjectURL', {
      configurable: true,
      writable: true,
      value: vi.fn(),
    })
  })

  afterEach(() => {
    if (origCreate) {
      Object.defineProperty(URL, 'createObjectURL', { configurable: true, writable: true, value: origCreate })
    } else {
      delete (URL as unknown as { createObjectURL?: unknown }).createObjectURL
    }
    if (origRevoke) {
      Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, writable: true, value: origRevoke })
    } else {
      delete (URL as unknown as { revokeObjectURL?: unknown }).revokeObjectURL
    }
  })

  it('runTraceExportFilename is deterministic', () => {
    expect(runTraceExportFilename(42)).toBe('contextlens-run-42.json')
  })

  it('serializeRunTraceJson round-trips run detail shape', () => {
    const run = minimalRun({ run_id: 7 })
    const parsed = JSON.parse(serializeRunTraceJson(run)) as RunDetail
    expect(parsed.run_id).toBe(7)
    expect(parsed.query_case.query_text).toBe('q')
  })

  it('dashboard JSON filenames are stable', () => {
    expect(dashboardExportJsonFilename()).toBe('contextlens-dashboard.json')
    expect(dashboardExportCsvFilename()).toBe('contextlens-dashboard.csv')
  })

  it('buildDashboardExportBundle preserves null analytics', () => {
    const s = tinySummary()
    const b = buildDashboardExportBundle(s, null, '2026-03-21T00:00:00.000Z')
    expect(b.dashboard_summary).toBe(s)
    expect(b.dashboard_analytics).toBeNull()
    const raw = serializeDashboardExportJson(b)
    expect(raw).toContain('"dashboard_analytics": null')
  })

  it('csvEscapeCell escapes commas and quotes', () => {
    expect(csvEscapeCell('a,b')).toBe('"a,b"')
    expect(csvEscapeCell('say "hi"')).toBe('"say ""hi"""')
    expect(csvEscapeCell(null)).toBe('')
    expect(csvEscapeCell(undefined)).toBe('')
  })

  it('joinCsvRow builds a line', () => {
    expect(joinCsvRow([1, 'x', null])).toBe('1,x,')
  })

  it('buildDashboardExportCsv with no data returns honest placeholder', () => {
    const csv = buildDashboardExportCsv(null, null)
    expect(csv).toContain('no_data_loaded')
  })

  it('buildDashboardExportCsv summary-only omits analytics-only sections', () => {
    const csv = buildDashboardExportCsv(tinySummary(), null)
    expect(csv).toContain('section,recent_runs')
    expect(csv).toMatch(/\n5,completed,2026-03-01T00:00:00Z,/)
    expect(csv).toContain('end_to_end_run_latency_avg_sec,0.02')
    expect(csv).toContain('scale_benchmark_datasets,1')
    expect(csv).toContain('scale_chunks_indexed,5')
    expect(csv).toContain('cost_llm_runs_with_measured_cost,0')
    expect(csv).toContain('cost_full_rag_runs_with_measured_cost,0')
    expect(csv).not.toContain('section,time_series_daily')
  })

  it('buildDashboardExportCsv analytics-only still renders analytics blocks', () => {
    const csv = buildDashboardExportCsv(null, tinyAnalytics())
    expect(csv).toContain('section,end_to_end_run_latency_sec')
    expect(csv).toContain('end_to_end_run_latency_avg_sec,0.1')
    expect(csv).toContain('end_to_end_run_latency_p95_sec,0.11')
    expect(csv).toContain('section,time_series_daily')
    expect(csv).toContain('2026-03-20')
    expect(csv).toContain('section,config_insights_heuristic')
    expect(csv).toContain('section,config_insights_llm')
    expect(csv).toContain('cfg""a')
    expect(csv).not.toContain('section,recent_runs')
  })

  it('buildDashboardExportCsv tolerates partial / missing nested fields', () => {
    const brokenSummary = {
      total_runs: 0,
      status_counts: undefined,
      evaluator_counts: undefined,
      latency: undefined,
      cost: undefined,
      failure_type_counts: undefined,
      recent_runs: undefined,
    } as unknown as DashboardSummaryResponse

    const brokenAnalytics = {
      time_series: null,
      latency_distribution: null,
      failure_analysis: undefined,
      config_insights: undefined,
    } as unknown as DashboardAnalyticsResponse

    expect(() => buildDashboardExportCsv(brokenSummary, brokenAnalytics)).not.toThrow()
    const csv = buildDashboardExportCsv(brokenSummary, brokenAnalytics)
    expect(csv.length).toBeGreaterThan(0)
  })

  it('triggerBrowserDownload creates a blob download', () => {
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    const createUrl = URL.createObjectURL as ReturnType<typeof vi.fn>
    const revoke = URL.revokeObjectURL as ReturnType<typeof vi.fn>

    triggerBrowserDownload('out.json', '{"a":1}\n', 'application/json')

    expect(createUrl).toHaveBeenCalled()
    const blobArg = createUrl.mock.calls[0][0] as Blob
    expect(blobArg.type).toBe('application/json')

    expect(click).toHaveBeenCalled()
    expect(revoke).toHaveBeenCalledWith('blob:unit-test')

    click.mockRestore()
  })
})
