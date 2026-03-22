import { useCallback, useEffect, useMemo, useState } from 'react'
import { api } from '../api/client'
import type {
  ConfigComparisonMetrics,
  ConfigComparisonResponse,
  DashboardAnalyticsResponse,
  DashboardSummaryResponse,
} from '../api/types'
import { describeApiError } from './errorMessage'
import { costAvailabilityLine, formatLatencyMs, formatLatencySec, formatUsd } from './dashboardFormat'
import { DashboardTrendPanel } from './DashboardTrendPanel'
import { LatencyDistributionPanel } from './LatencyDistributionPanel'
import { FailureBreakdownPanel } from './FailureBreakdownPanel'
import { ConfigInsightsPanel } from './ConfigInsightsPanel'
import {
  buildDashboardExportBundle,
  buildDashboardExportCsv,
  dashboardExportCsvFilename,
  dashboardExportJsonFilename,
  serializeDashboardExportJson,
  triggerBrowserDownload,
} from './exportDownload'
import { ScoreComparisonDl } from './scoreComparisonDisplay'

function formatWhen(iso: string): string {
  try {
    return new Date(iso).toLocaleString()
  } catch {
    return iso
  }
}

function RunStatusBadge({ status }: { status: string }) {
  const cls = `cl-run-badge cl-run-badge--${status.replace(/_/g, '-')}`
  return (
    <span className={cls} title={status}>
      {status.replace(/_/g, ' ')}
    </span>
  )
}

function CompareBucketsTable({ result }: { result: ConfigComparisonResponse }) {
  const buckets = result.buckets
  if (result.evaluator_type !== 'both' || buckets == null) {
    return null
  }
  const scb = result.score_comparison_buckets
  return (
    <div className="cl-dash-compare-buckets">
      {(['heuristic', 'llm'] as const).map((bucket) => (
        <div key={bucket} className="cl-card cl-dash-bucket">
          <h3>Pipeline configs — {bucket}</h3>
          {scb?.[bucket] ? <ScoreComparisonDl summary={scb[bucket]!} /> : null}
          <CompareMetricsRows rows={buckets[bucket] ?? []} />
        </div>
      ))}
    </div>
  )
}

function CompareMetricsRows({ rows }: { rows: ConfigComparisonMetrics[] }) {
  if (!rows.length) {
    return <p className="cl-muted">No rows.</p>
  }
  return (
    <div className="cl-table-wrap">
      <table className="cl-table">
        <thead>
          <tr>
            <th>Config id</th>
            <th>Traced</th>
            <th>Avg total ms</th>
            <th>Avg cost USD</th>
            <th>Failures (top)</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((m) => {
            const fc = m.failure_type_counts || {}
            const top = Object.entries(fc)
              .sort((a, b) => b[1] - a[1])
              .slice(0, 3)
            const failStr =
              top.length === 0 ? '—' : top.map(([k, v]) => `${k}: ${v}`).join('; ')
            return (
              <tr key={m.pipeline_config_id}>
                <td>{m.pipeline_config_id}</td>
                <td>{m.traced_runs}</td>
                <td>{m.avg_total_latency_ms != null ? m.avg_total_latency_ms.toFixed(1) : '—'}</td>
                <td>
                  {m.avg_evaluation_cost_per_run_usd != null
                    ? formatUsd(m.avg_evaluation_cost_per_run_usd)
                    : '—'}
                </td>
                <td className="cl-td-wrap">{failStr}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

export type DashboardPanelProps = {
  /** Used for optional per-config comparison (capped server-side). */
  pipelineConfigIds: number[]
  onOpenRunDetail?: (runId: number) => void
}

const MAX_COMPARE_IDS = 12

export function DashboardPanel({ pipelineConfigIds, onOpenRunDetail }: DashboardPanelProps) {
  const [data, setData] = useState<DashboardSummaryResponse | null>(null)
  const [analytics, setAnalytics] = useState<DashboardAnalyticsResponse | null>(null)
  const [compare, setCompare] = useState<ConfigComparisonResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [compareLoading, setCompareLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Avoid unstable `[]` reference from inline props — prevents loadAll/useEffect loops.
  const pipelineConfigIdsKey =
    pipelineConfigIds.length > 0 ? pipelineConfigIds.join(',') : '__empty__'
  const compareIds = useMemo(
    () => pipelineConfigIds.slice(0, MAX_COMPARE_IDS),
    [pipelineConfigIdsKey], // eslint-disable-line react-hooks/exhaustive-deps -- key encodes id list
  )

  const loadAll = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [d, a] = await Promise.all([api.dashboardSummary(), api.dashboardAnalytics()])
      setData(d)
      setAnalytics(a)
      if (compareIds.length > 0) {
        setCompareLoading(true)
        try {
          const c = await api.configComparison(compareIds, { evaluatorType: 'both' })
          setCompare(c)
        } catch {
          setCompare(null)
        } finally {
          setCompareLoading(false)
        }
      } else {
        setCompare(null)
        setCompareLoading(false)
      }
    } catch (e) {
      setData(null)
      setAnalytics(null)
      setCompare(null)
      setError(describeApiError(e))
    } finally {
      setLoading(false)
    }
  }, [compareIds])

  useEffect(() => {
    void loadAll()
  }, [loadAll])

  const failureEntries = data
    ? Object.entries(data.failure_type_counts).sort((a, b) => b[1] - a[1])
    : []

  return (
    <div className="cl-dashboard">
      <section className="cl-card cl-dash-header">
        <div className="cl-dash-header-row">
          <h2>Observability</h2>
          <div className="cl-dash-header-actions">
            <button
              type="button"
              className="cl-btn cl-btn-secondary cl-btn-sm"
              data-testid="dashboard-export-json"
              disabled={loading || error != null || !data}
              onClick={() => {
                if (!data) {
                  return
                }
                const bundle = buildDashboardExportBundle(
                  data,
                  analytics,
                  new Date().toISOString(),
                )
                triggerBrowserDownload(
                  dashboardExportJsonFilename(),
                  serializeDashboardExportJson(bundle),
                  'application/json',
                )
              }}
            >
              Export JSON
            </button>
            <button
              type="button"
              className="cl-btn cl-btn-secondary cl-btn-sm"
              data-testid="dashboard-export-csv"
              disabled={loading || error != null || !data}
              onClick={() => {
                if (!data) {
                  return
                }
                triggerBrowserDownload(
                  dashboardExportCsvFilename(),
                  buildDashboardExportCsv(data, analytics),
                  'text/csv;charset=utf-8',
                )
              }}
            >
              Export CSV
            </button>
            <button
              type="button"
              className="cl-btn cl-btn-secondary cl-btn-sm"
              onClick={() => void loadAll()}
              disabled={loading}
            >
              {loading ? 'Refreshing…' : 'Refresh'}
            </button>
          </div>
        </div>
        <p className="cl-muted">
          Live aggregates from <code>GET /api/v1/runs/dashboard-summary</code>. Costs reflect stored{' '}
          <code>evaluation_results.cost_usd</code> (N/A when null — not the same as $0).
        </p>
      </section>

      {error ? (
        <div className="cl-msg cl-msg-error" role="alert">
          {error}
        </div>
      ) : null}

      {loading && !data ? (
        <p className="cl-loading" aria-live="polite">
          Loading dashboard…
        </p>
      ) : null}

      {data && !error ? (
        <>
          <section className="cl-dash-grid" aria-label="System scale" data-testid="dashboard-system-scale">
            <div className="cl-dash-stat">
              <span className="cl-dash-stat-label">Benchmark datasets</span>
              <span className="cl-dash-stat-value">{data.scale.benchmark_datasets}</span>
            </div>
            <div className="cl-dash-stat">
              <span className="cl-dash-stat-label">Query cases</span>
              <span className="cl-dash-stat-value">{data.scale.total_queries}</span>
            </div>
            <div className="cl-dash-stat">
              <span className="cl-dash-stat-label">Traced runs</span>
              <span className="cl-dash-stat-value">{data.scale.total_traced_runs}</span>
            </div>
            <div className="cl-dash-stat">
              <span className="cl-dash-stat-label">Configs in runs</span>
              <span className="cl-dash-stat-value">{data.scale.configs_tested}</span>
            </div>
            <div className="cl-dash-stat">
              <span className="cl-dash-stat-label">Documents processed</span>
              <span className="cl-dash-stat-value">{data.scale.documents_processed}</span>
            </div>
            <div className="cl-dash-stat">
              <span className="cl-dash-stat-label">Chunks stored</span>
              <span className="cl-dash-stat-value">{data.scale.chunks_indexed}</span>
            </div>
          </section>
          <p className="cl-muted cl-dash-scale-note">
            <strong>Traced runs</strong> = runs with at least one persisted retrieval hit and one evaluation row
            (same definition as metrics aggregate). <strong>Configs in runs</strong> = distinct{' '}
            <code>pipeline_config_id</code> on run rows. <strong>Chunks stored</strong> = rows in{' '}
            <code>chunks</code> (ingested segments; aligns with aggregate <code>chunk_count</code>).
          </p>

          <section className="cl-dash-grid" aria-label="Run counts">
            <div className="cl-dash-stat">
              <span className="cl-dash-stat-label">Total runs</span>
              <span className="cl-dash-stat-value">{data.total_runs}</span>
            </div>
            <div className="cl-dash-stat">
              <span className="cl-dash-stat-label">Completed</span>
              <span className="cl-dash-stat-value">{data.status_counts.completed}</span>
            </div>
            <div className="cl-dash-stat">
              <span className="cl-dash-stat-label">Failed</span>
              <span className="cl-dash-stat-value">{data.status_counts.failed}</span>
            </div>
            <div className="cl-dash-stat">
              <span className="cl-dash-stat-label">In progress</span>
              <span className="cl-dash-stat-value">{data.status_counts.in_progress}</span>
            </div>
            <div className="cl-dash-stat">
              <span className="cl-dash-stat-label">Heuristic (eval rows)</span>
              <span className="cl-dash-stat-value">{data.evaluator_counts.heuristic_runs}</span>
            </div>
            <div className="cl-dash-stat">
              <span className="cl-dash-stat-label">LLM (eval rows)</span>
              <span className="cl-dash-stat-value">{data.evaluator_counts.llm_runs}</span>
            </div>
            <div className="cl-dash-stat cl-dash-stat-wide">
              <span className="cl-dash-stat-label">Runs without evaluation</span>
              <span className="cl-dash-stat-value">{data.evaluator_counts.runs_without_evaluation}</span>
            </div>
          </section>

          <DashboardTrendPanel
            isRefreshing={loading && analytics != null}
            timeSeries={analytics?.time_series ?? []}
          />

          <section className="cl-card" aria-label="Latency">
            <h2>Latency</h2>
            <p className="cl-muted">
              Means and retrieval percentiles are computed server-side from persisted{' '}
              <code>runs.*_latency_ms</code> only (PostgreSQL <code>percentile_cont</code> for P50/P95).
              End-to-end average and P95 in seconds use the same non-null{' '}
              <code>runs.total_latency_ms</code> population as the total mean (milliseconds); seconds = ms ÷
              1000.
            </p>
            <dl className="cl-dash-dl">
              <div className="cl-dash-dl-row" data-testid="dashboard-retrieval-latency">
                <dt>Retrieval</dt>
                <dd>
                  <ul className="cl-dash-latency-breakdown">
                    <li>
                      <span className="cl-dash-latency-label">Mean</span>{' '}
                      {formatLatencyMs(data.latency.avg_retrieval_latency_ms)}
                    </li>
                    <li>
                      <span className="cl-dash-latency-label">P50</span>{' '}
                      {formatLatencyMs(data.latency.retrieval_latency_p50_ms)}
                    </li>
                    <li>
                      <span className="cl-dash-latency-label">P95</span>{' '}
                      {formatLatencyMs(data.latency.retrieval_latency_p95_ms)}
                    </li>
                  </ul>
                </dd>
              </div>
              <div className="cl-dash-dl-row">
                <dt>Generation</dt>
                <dd>{formatLatencyMs(data.latency.avg_generation_latency_ms)}</dd>
              </div>
              <div className="cl-dash-dl-row">
                <dt>Evaluation</dt>
                <dd>{formatLatencyMs(data.latency.avg_evaluation_latency_ms)}</dd>
              </div>
              <div className="cl-dash-dl-row" data-testid="dashboard-end-to-end-latency">
                <dt>End-to-end (total)</dt>
                <dd>
                  <ul className="cl-dash-latency-breakdown">
                    <li>
                      <span className="cl-dash-latency-label">Mean (ms)</span>{' '}
                      {formatLatencyMs(data.latency.avg_total_latency_ms)}
                    </li>
                    <li>
                      <span className="cl-dash-latency-label">Avg (s)</span>{' '}
                      {formatLatencySec(data.latency.end_to_end_run_latency_avg_sec)}
                    </li>
                    <li>
                      <span className="cl-dash-latency-label">P95 (s)</span>{' '}
                      {formatLatencySec(data.latency.end_to_end_run_latency_p95_sec)}
                    </li>
                  </ul>
                </dd>
              </div>
            </dl>
          </section>

          <section className="cl-card" aria-label="Cost summary">
            <h2>LLM cost (evaluation rows)</h2>
            <p className="cl-muted">{costAvailabilityLine(data.cost)}</p>
            <dl className="cl-dash-dl">
              <div className="cl-dash-dl-row">
                <dt>Total (sum of non-null)</dt>
                <dd>{formatUsd(data.cost.total_cost_usd)}</dd>
              </div>
              <div className="cl-dash-dl-row">
                <dt>Average per evaluation row (non-null only)</dt>
                <dd>{formatUsd(data.cost.avg_cost_usd)}</dd>
              </div>
              <div className="cl-dash-dl-row">
                <dt>Average per LLM run (measured cost only)</dt>
                <dd>
                  {formatUsd(data.cost.avg_cost_usd_per_llm_run)}{' '}
                  <span className="cl-muted">
                    ({data.cost.llm_runs_with_measured_cost} run
                    {data.cost.llm_runs_with_measured_cost === 1 ? '' : 's'} with non-null cost; heuristic
                    excluded)
                  </span>
                </dd>
              </div>
              <div className="cl-dash-dl-row">
                <dt>Average per full RAG run (gen + judge, measured)</dt>
                <dd>
                  {formatUsd(data.cost.avg_cost_usd_per_full_rag_run)}{' '}
                  <span className="cl-muted">
                    ({data.cost.full_rag_runs_with_measured_cost} run
                    {data.cost.full_rag_runs_with_measured_cost === 1 ? '' : 's'} with{' '}
                    <code>generation_results</code> + LLM cost)
                  </span>
                </dd>
              </div>
            </dl>
          </section>

          <section className="cl-card" aria-label="Failure types">
            <h2>Failure types</h2>
            {failureEntries.length === 0 ? (
              <p className="cl-muted cl-empty-inline">No failure labels recorded on evaluations yet.</p>
            ) : (
              <div className="cl-table-wrap">
                <table className="cl-table">
                  <thead>
                    <tr>
                      <th>Failure type</th>
                      <th>Count</th>
                    </tr>
                  </thead>
                  <tbody>
                    {failureEntries.map(([k, v]) => (
                      <tr key={k}>
                        <td>
                          <strong>{k}</strong>
                        </td>
                        <td>{v}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <section className="cl-card" aria-label="Recent runs">
            <h2>Recent runs</h2>
            {data.recent_runs.length === 0 ? (
              <p className="cl-muted cl-empty-inline">No runs in the database yet.</p>
            ) : (
              <div className="cl-table-wrap">
                <table className="cl-table">
                  <thead>
                    <tr>
                      <th>ID</th>
                      <th>When</th>
                      <th>Status</th>
                      <th>Evaluator</th>
                      <th>Total ms</th>
                      <th>Cost</th>
                      <th>Failure</th>
                      {onOpenRunDetail ? <th /> : null}
                    </tr>
                  </thead>
                  <tbody>
                    {data.recent_runs.map((r) => (
                      <tr key={r.run_id}>
                        <td>{r.run_id}</td>
                        <td>{formatWhen(r.created_at)}</td>
                        <td>
                          <RunStatusBadge status={r.status} />
                        </td>
                        <td>{r.evaluator_type}</td>
                        <td>{formatLatencyMs(r.total_latency_ms)}</td>
                        <td>{formatUsd(r.cost_usd)}</td>
                        <td className="cl-td-wrap">{r.failure_type ?? '—'}</td>
                        {onOpenRunDetail ? (
                          <td>
                            <button
                              type="button"
                              className="cl-btn cl-btn-secondary cl-btn-sm"
                              onClick={() => onOpenRunDetail(r.run_id)}
                            >
                              Detail
                            </button>
                          </td>
                        ) : null}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          {analytics ? (
            <>
              <LatencyDistributionPanel data={analytics.latency_distribution} />
              <FailureBreakdownPanel
                data={analytics.failure_analysis}
                onOpenRunDetail={onOpenRunDetail}
              />
              <ConfigInsightsPanel data={analytics.config_insights} />
            </>
          ) : null}

          {compareIds.length > 0 ? (
            <section className="cl-card" aria-label="Config comparison snapshot">
              <h2>Per-pipeline config snapshot</h2>
              <p className="cl-muted">
                From <code>GET /runs/config-comparison</code> for up to {MAX_COMPARE_IDS} configs (
                {compareIds.length} selected). Traced runs only.
              </p>
              {compareLoading ? (
                <p className="cl-loading-inline">Loading comparison…</p>
              ) : compare ? (
                <CompareBucketsTable result={compare} />
              ) : (
                <p className="cl-muted">Comparison unavailable (no data or request failed).</p>
              )}
            </section>
          ) : null}
        </>
      ) : null}
    </div>
  )
}
