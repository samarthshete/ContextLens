import type {
  ConfigInsight,
  DashboardAnalyticsResponse,
  DashboardRecentRun,
  DashboardSummaryResponse,
  RunDetail,
  TimeSeriesDay,
} from '../api/types'

/** RFC 4180–style cell escaping for CSV rows. */
export function csvEscapeCell(value: unknown): string {
  if (value === null || value === undefined) {
    return ''
  }
  const s = String(value)
  if (/[",\r\n]/.test(s)) {
    return `"${s.replace(/"/g, '""')}"`
  }
  return s
}

export function joinCsvRow(cells: unknown[]): string {
  return cells.map(csvEscapeCell).join(',')
}

export function runTraceExportFilename(runId: number): string {
  return `contextlens-run-${runId}.json`
}

export function serializeRunTraceJson(run: RunDetail): string {
  return `${JSON.stringify(run, null, 2)}\n`
}

export type DashboardExportBundle = {
  exported_at: string
  dashboard_summary: DashboardSummaryResponse | null
  dashboard_analytics: DashboardAnalyticsResponse | null
}

export function buildDashboardExportBundle(
  summary: DashboardSummaryResponse | null,
  analytics: DashboardAnalyticsResponse | null,
  exportedAtIso: string,
): DashboardExportBundle {
  return {
    exported_at: exportedAtIso,
    dashboard_summary: summary,
    dashboard_analytics: analytics,
  }
}

export function dashboardExportJsonFilename(): string {
  return 'contextlens-dashboard.json'
}

export function dashboardExportCsvFilename(): string {
  return 'contextlens-dashboard.csv'
}

export function serializeDashboardExportJson(bundle: DashboardExportBundle): string {
  return `${JSON.stringify(bundle, null, 2)}\n`
}

function pushMetricRows(
  lines: string[],
  label: string,
  rows: Array<[string, string | number | null | undefined]>,
): void {
  lines.push(joinCsvRow(['section', label]))
  lines.push(joinCsvRow(['metric', 'value']))
  for (const [k, v] of rows) {
    lines.push(joinCsvRow([k, v]))
  }
  lines.push('')
}

function recentRunsHeader(): string[] {
  return [
    'run_id',
    'status',
    'created_at',
    'evaluator_type',
    'total_latency_ms',
    'cost_usd',
    'failure_type',
  ]
}

function recentRunRow(r: DashboardRecentRun): unknown[] {
  return [
    r.run_id,
    r.status,
    r.created_at,
    r.evaluator_type,
    r.total_latency_ms ?? '',
    r.cost_usd ?? '',
    r.failure_type ?? '',
  ]
}

function configInsightHeader(): string[] {
  return [
    'pipeline_config_id',
    'pipeline_config_name',
    'traced_runs',
    'completed_runs',
    'failed_runs',
    'avg_total_latency_ms',
    'min_total_latency_ms',
    'max_total_latency_ms',
    'avg_cost_usd',
    'total_cost_usd',
    'avg_retrieval_relevance',
    'avg_context_coverage',
    'avg_completeness',
    'avg_faithfulness',
    'latest_run_at',
    'top_failure_type',
  ]
}

function configInsightRow(c: ConfigInsight): unknown[] {
  return [
    c.pipeline_config_id,
    c.pipeline_config_name,
    c.traced_runs,
    c.completed_runs,
    c.failed_runs,
    c.avg_total_latency_ms ?? '',
    c.min_total_latency_ms ?? '',
    c.max_total_latency_ms ?? '',
    c.avg_cost_usd ?? '',
    c.total_cost_usd ?? '',
    c.avg_retrieval_relevance ?? '',
    c.avg_context_coverage ?? '',
    c.avg_completeness ?? '',
    c.avg_faithfulness ?? '',
    c.latest_run_at ?? '',
    c.top_failure_type ?? '',
  ]
}

function timeSeriesHeader(): string[] {
  return [
    'date',
    'runs',
    'completed',
    'failed',
    'avg_total_latency_ms',
    'avg_cost_usd',
    'failure_count',
  ]
}

function timeSeriesRow(d: TimeSeriesDay): unknown[] {
  return [
    d.date,
    d.runs,
    d.completed,
    d.failed,
    d.avg_total_latency_ms ?? '',
    d.avg_cost_usd ?? '',
    d.failure_count,
  ]
}

/**
 * Flatten dashboard summary + analytics into a simple multi-section CSV (blank line between sections).
 * Omits sections when the source object is null; never throws on empty arrays or missing nested keys.
 */
export function buildDashboardExportCsv(
  summary: DashboardSummaryResponse | null,
  analytics: DashboardAnalyticsResponse | null,
): string {
  const lines: string[] = []

  if (!summary && !analytics) {
    lines.push(joinCsvRow(['contextlens_dashboard_csv', 'no_data_loaded']))
    lines.push('')
    return lines.join('\n')
  }

  if (summary) {
    pushMetricRows(lines, 'summary_counts', [
      ['total_runs', summary.total_runs],
      ['status_completed', summary.status_counts?.completed],
      ['status_failed', summary.status_counts?.failed],
      ['status_in_progress', summary.status_counts?.in_progress],
      ['evaluator_heuristic_runs', summary.evaluator_counts?.heuristic_runs],
      ['evaluator_llm_runs', summary.evaluator_counts?.llm_runs],
      ['evaluator_runs_without_evaluation', summary.evaluator_counts?.runs_without_evaluation],
      ['latency_avg_retrieval_ms', summary.latency?.avg_retrieval_latency_ms],
      ['latency_avg_generation_ms', summary.latency?.avg_generation_latency_ms],
      ['latency_avg_evaluation_ms', summary.latency?.avg_evaluation_latency_ms],
      ['latency_avg_total_ms', summary.latency?.avg_total_latency_ms],
      ['cost_total_usd', summary.cost?.total_cost_usd],
      ['cost_avg_usd', summary.cost?.avg_cost_usd],
      ['cost_rows_with_value', summary.cost?.evaluation_rows_with_cost],
      ['cost_rows_not_available', summary.cost?.evaluation_rows_cost_not_available],
    ])

    const fc = summary.failure_type_counts && typeof summary.failure_type_counts === 'object'
      ? summary.failure_type_counts
      : {}
    lines.push(joinCsvRow(['section', 'failure_type_counts']))
    lines.push(joinCsvRow(['failure_type', 'count']))
    const entries = Object.entries(fc).sort((a, b) => b[1] - a[1])
    for (const [k, v] of entries) {
      lines.push(joinCsvRow([k, v]))
    }
    lines.push('')

    const recent = Array.isArray(summary.recent_runs) ? summary.recent_runs : []
    lines.push(joinCsvRow(['section', 'recent_runs']))
    lines.push(joinCsvRow(recentRunsHeader()))
    for (const r of recent) {
      lines.push(joinCsvRow(recentRunRow(r)))
    }
    lines.push('')
  }

  if (analytics) {
    const dist = analytics.latency_distribution
    if (dist && typeof dist === 'object') {
      lines.push(joinCsvRow(['section', 'latency_distribution']))
      lines.push(joinCsvRow(['phase', 'count', 'min_ms', 'max_ms', 'avg_ms', 'median_ms', 'p95_ms']))
      const phases = ['retrieval', 'generation', 'evaluation', 'total'] as const
      for (const p of phases) {
        const row = dist[p]
        if (!row || typeof row !== 'object') {
          lines.push(joinCsvRow([p, '', '', '', '', '', '']))
          continue
        }
        lines.push(
          joinCsvRow([
            p,
            row.count,
            row.min_ms ?? '',
            row.max_ms ?? '',
            row.avg_ms ?? '',
            row.median_ms ?? '',
            row.p95_ms ?? '',
          ]),
        )
      }
      lines.push('')
    }

    const ts = Array.isArray(analytics.time_series) ? analytics.time_series : []
    lines.push(joinCsvRow(['section', 'time_series_daily']))
    lines.push(joinCsvRow(timeSeriesHeader()))
    for (const d of ts) {
      if (d && typeof d === 'object') {
        lines.push(joinCsvRow(timeSeriesRow(d)))
      }
    }
    lines.push('')

    const insights = Array.isArray(analytics.config_insights) ? analytics.config_insights : []
    lines.push(joinCsvRow(['section', 'config_insights']))
    lines.push(joinCsvRow(configInsightHeader()))
    for (const c of insights) {
      if (c && typeof c === 'object') {
        lines.push(joinCsvRow(configInsightRow(c)))
      }
    }
    lines.push('')
  }

  return lines.join('\n')
}

export function triggerBrowserDownload(filename: string, content: string, mimeType: string): void {
  const blob = new Blob([content], { type: mimeType })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.rel = 'noopener'
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}
