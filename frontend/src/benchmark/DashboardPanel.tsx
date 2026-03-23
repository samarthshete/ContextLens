import { useCallback, useEffect, useMemo, useState } from 'react'
import { api } from '../api/client'
import type {
  ConfigComparisonMetrics,
  ConfigComparisonResponse,
  DashboardAnalyticsResponse,
  DashboardSummaryResponse,
  Dataset,
} from '../api/types'
import { describeApiError } from './errorMessage'
import { costAvailabilityLine, formatLatencyMs, formatLatencySec, formatUsd } from './dashboardFormat'
import { DASHBOARD_COMPARE_MIN_RUNS_FOR_TABLE, DASHBOARD_LLM_SPARSE_GATE_RUNS } from './dashboardConstants'
import { DashboardTrendPanel } from './DashboardTrendPanel'
import { LatencyDistributionPanel } from './LatencyDistributionPanel'
import { FailureBreakdownPanel } from './FailureBreakdownPanel'
import { ConfigInsightsBucketSection } from './ConfigInsightsPanel'
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

/** Default dashboard selection: newest registry row by `created_at`. */
export function pickLatestDatasetId(datasets: Dataset[]): number | null {
  if (datasets.length === 0) return null
  const sorted = [...datasets].sort((a, b) => b.created_at.localeCompare(a.created_at))
  return sorted[0]!.id
}

function RunStatusBadge({ status }: { status: string }) {
  const cls = `cl-run-badge cl-run-badge--${status.replace(/_/g, '-')}`
  return (
    <span className={cls} title={status}>
      {status.replace(/_/g, ' ')}
    </span>
  )
}

function ComparisonReliabilityBanner({ result }: { result: ConfigComparisonResponse }) {
  const conf = result.comparison_confidence ?? 'LOW'
  const reliable = result.comparison_statistically_reliable ?? false
  const ess = result.effective_sample_size ?? 0
  const uq = result.unique_queries_compared ?? 0
  const minReq = result.recommended_min_unique_queries_for_valid_comparison ?? 10

  const confCls =
    conf === 'HIGH' ? 'cl-badge--ok' : conf === 'MEDIUM' ? 'cl-badge--info' : 'cl-badge--warn'

  // Check if any config has zero runs
  const allRows = [
    ...(result.configs ?? []),
    ...(result.buckets ? Object.values(result.buckets).flat() : []),
  ]
  const hasZeroConfig = allRows.some((r) => r.traced_runs === 0)
  const minTraced = result.min_traced_runs_across_configs ?? 0

  if (hasZeroConfig) {
    return (
      <p className="cl-msg cl-msg-error" data-testid="compare-zero-runs-warning" role="alert">
        One or more configs have no traced runs — comparison not possible.
      </p>
    )
  }

  return (
    <div className="cl-compare-reliability" data-testid="compare-reliability-banner">
      <div className="cl-compare-reliability-badges">
        <span className={`cl-badge ${confCls}`} data-testid="compare-confidence-badge">
          Confidence: {conf}
        </span>
        {!reliable ? (
          <span className="cl-badge cl-badge--warn" data-testid="compare-not-reliable-badge">
            Not statistically reliable
          </span>
        ) : null}
      </div>
      <p className="cl-muted" data-testid="compare-effective-sample">
        Effective sample size: <strong>{ess}</strong> unique queries (min across configs).
        {uq < minReq ? (
          <> Recommended minimum: {minReq} distinct queries for valid comparison.</>
        ) : null}
      </p>
      {minTraced < DASHBOARD_COMPARE_MIN_RUNS_FOR_TABLE ? (
        <p className="cl-msg cl-msg-warn" data-testid="compare-insufficient-runs-warning" role="alert">
          Insufficient runs for reliable comparison (min recommended: {DASHBOARD_COMPARE_MIN_RUNS_FOR_TABLE}).
          Treat results as directional only.
        </p>
      ) : null}
    </div>
  )
}

function CompareBucketsTable({
  result,
  llmEvalRunCount,
}: {
  result: ConfigComparisonResponse
  llmEvalRunCount: number
}) {
  const buckets = result.buckets
  if (result.evaluator_type !== 'both' || buckets == null) {
    return null
  }
  const scb = result.score_comparison_buckets

  // Distinct query display for repeated sampling context
  const hRows = buckets.heuristic ?? []
  const hTotalTraced = hRows.reduce((a, r) => a + r.traced_runs, 0)
  const hDistinctQueries = hRows.length > 0 ? Math.max(...hRows.map((r) => r.unique_query_count ?? 0)) : 0

  return (
    <div className="cl-dash-compare-buckets">
      <ComparisonReliabilityBanner result={result} />
      {hTotalTraced > 0 && hDistinctQueries > 0 ? (
        <p className="cl-muted" data-testid="compare-repeated-sampling">
          Runs: {hTotalTraced} across {hDistinctQueries} unique queries (repeated sampling)
        </p>
      ) : null}
      <div className="cl-card cl-dash-bucket">
        <h3>Pipeline configs — heuristic</h3>
        {scb?.heuristic ? (
          <ScoreComparisonDl summary={scb.heuristic} metricsRows={buckets.heuristic ?? []} />
        ) : null}
        <CompareMetricsRows rows={buckets.heuristic ?? []} />
      </div>
      <div className="cl-card cl-dash-bucket">
        <h3>Pipeline configs — llm</h3>
        {llmEvalRunCount < DASHBOARD_LLM_SPARSE_GATE_RUNS ? (
          <p className="cl-msg cl-msg-warn" data-testid="dashboard-llm-compare-sparse-gate" role="alert">
            ⚠ Sparse sample ({llmEvalRunCount} run{llmEvalRunCount === 1 ? '' : 's'}) — not reliable
          </p>
        ) : (
          <>
            {scb?.llm ? (
              <ScoreComparisonDl summary={scb.llm} metricsRows={buckets.llm ?? []} />
            ) : null}
            <CompareMetricsRows rows={buckets.llm ?? []} />
          </>
        )}
      </div>
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
            <th>Distinct queries</th>
            <th>Avg total ms</th>
            <th>Avg cost USD</th>
            <th>Eval failure labels (top)</th>
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
                <td>{m.unique_query_count ?? '—'}</td>
                <td>{m.avg_total_latency_ms != null ? Math.round(m.avg_total_latency_ms) : '—'}</td>
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
  /** Benchmark datasets from registry; dashboard aggregates are scoped by selection. */
  datasets: Dataset[]
  registryLoading: boolean
  onOpenRunDetail?: (runId: number) => void
}

const MAX_COMPARE_IDS = 12

export function DashboardPanel({
  pipelineConfigIds,
  datasets,
  registryLoading,
  onOpenRunDetail,
}: DashboardPanelProps) {
  const [selectedDatasetId, setSelectedDatasetId] = useState<number | null>(null)
  const [data, setData] = useState<DashboardSummaryResponse | null>(null)
  const [analytics, setAnalytics] = useState<DashboardAnalyticsResponse | null>(null)
  const [compare, setCompare] = useState<ConfigComparisonResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [compareLoading, setCompareLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (datasets.length === 0) {
      setSelectedDatasetId(null)
      return
    }
    setSelectedDatasetId((prev) => {
      if (prev != null && datasets.some((d) => d.id === prev)) return prev
      return pickLatestDatasetId(datasets)
    })
  }, [datasets])

  // Avoid unstable `[]` reference from inline props — prevents loadAll/useEffect loops.
  const pipelineConfigIdsKey =
    pipelineConfigIds.length > 0 ? pipelineConfigIds.join(',') : '__empty__'
  const compareIds = useMemo(
    () => pipelineConfigIds.slice(0, MAX_COMPARE_IDS),
    [pipelineConfigIdsKey], // eslint-disable-line react-hooks/exhaustive-deps -- key encodes id list
  )

  const loadAll = useCallback(async () => {
    if (selectedDatasetId == null) {
      setLoading(false)
      setError(null)
      setData(null)
      setAnalytics(null)
      setCompare(null)
      setCompareLoading(false)
      return
    }
    setLoading(true)
    setError(null)
    try {
      const [d, a] = await Promise.all([
        api.dashboardSummary({ datasetId: selectedDatasetId }),
        api.dashboardAnalytics({ datasetId: selectedDatasetId }),
      ])
      setData(d)
      setAnalytics(a)
      if (compareIds.length > 0) {
        setCompareLoading(true)
        try {
          const c = await api.configComparison(compareIds, {
            evaluatorType: 'both',
            datasetId: selectedDatasetId,
          })
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
  }, [compareIds, selectedDatasetId])

  useEffect(() => {
    void loadAll()
  }, [loadAll])

  const datasetSummary = useMemo(() => {
    if (selectedDatasetId == null) return null
    const d = datasets.find((x) => x.id === selectedDatasetId)
    return d ? `${d.name} (#${d.id})` : `Dataset #${selectedDatasetId}`
  }, [datasets, selectedDatasetId])

  const failureEntries = data
    ? Object.entries(data.failure_type_counts).sort((a, b) => b[1] - a[1])
    : []

  if (registryLoading) {
    return (
      <div className="cl-dashboard">
        <p className="cl-loading" data-testid="dashboard-registry-loading" aria-live="polite">
          Loading benchmark registry…
        </p>
      </div>
    )
  }

  if (datasets.length === 0) {
    return (
      <div className="cl-dashboard">
        <section className="cl-card cl-dash-header">
          <h2>Observability</h2>
        </section>
        <section className="cl-card" aria-label="Dataset required">
          <p className="cl-muted" data-testid="dashboard-select-dataset-msg">
            <strong>Select dataset to view analytics.</strong> No benchmark datasets yet — create one under{' '}
            <strong>Benchmark registry</strong> on the Run tab, then open the Dashboard again.
          </p>
        </section>
      </div>
    )
  }

  if (selectedDatasetId == null) {
    return (
      <div className="cl-dashboard">
        <p className="cl-loading" aria-live="polite">
          Preparing dataset…
        </p>
      </div>
    )
  }

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
        <div className="cl-field cl-dash-dataset-field">
          <label htmlFor="dashboard-dataset-select">Benchmark dataset</label>
          <select
            id="dashboard-dataset-select"
            data-testid="dashboard-dataset-select"
            value={selectedDatasetId}
            onChange={(e) => setSelectedDatasetId(Number(e.target.value))}
          >
            {datasets.map((d) => (
              <option key={d.id} value={d.id}>
                {d.name} (#{d.id})
              </option>
            ))}
          </select>
        </div>
        <p className="cl-muted">
          Scoped to <strong>{datasetSummary}</strong> via <code>?dataset_id=</code> on{' '}
          <code>GET /api/v1/runs/dashboard-summary</code> and <code>…/dashboard-analytics</code>. Costs reflect
          stored <code>evaluation_results.cost_usd</code> (N/A when null — not the same as $0).
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
              <span
                className="cl-dash-stat-label"
                title="Runs whose pipeline exited with status failed (errors, exhausted retries, etc.)."
              >
                System failures
              </span>
              <span className="cl-dash-stat-value" data-testid="dashboard-system-failures-count">
                {data.status_counts.failed}
              </span>
            </div>
            <div className="cl-dash-stat">
              <span
                className="cl-dash-stat-label"
                title="Evaluation rows where failure_type is set and not NO_FAILURE (retrieval/answer quality labels)."
              >
                Model failures
              </span>
              <span className="cl-dash-stat-value" data-testid="dashboard-model-failures-count">
                {data.model_failures ?? 0}
              </span>
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
          <p className="cl-muted cl-dash-scale-note">
            <strong>System failures</strong> = run <code>status</code> failed (pipeline did not complete successfully).{' '}
            <strong>Model failures</strong> = count of evaluation rows with a non–<code>NO_FAILURE</code> label (runs can
            still be <code>completed</code>).
          </p>

          <p className="cl-muted cl-dash-repeated-sampling" data-testid="dashboard-repeated-sampling-note">
            {data.repeated_sampling_note}
          </p>

          {data.model_failures > 0 && data.total_runs > 0 ? (
            <section
              className="cl-card cl-dash-model-quality-insight"
              aria-label="Model quality insight"
              data-testid="dashboard-model-quality-insight"
            >
              <p className="cl-dash-model-quality-insight-text">
                {data.status_counts.failed === 0
                  ? 'System is stable (0 system failures), but model quality is weak:'
                  : `System: ${data.status_counts.failed} system failure(s); separately, model-quality labels suggest:`}{' '}
                <strong>
                  {data.model_failures} model failure{data.model_failures === 1 ? '' : 's'} across {data.total_runs} runs ({((100 * data.model_failures) / data.total_runs).toFixed(1)}%)
                </strong>
                {(() => {
                  const entries = Object.entries(data.failure_type_counts)
                    .filter(([k]) => k !== 'NO_FAILURE')
                    .sort((a, b) => b[1] - a[1])
                  if (entries.length === 0) return '.'
                  const top = entries[0]!
                  const topPct = ((100 * top[1]) / data.model_failures).toFixed(0)
                  return `, dominated by ${top[0]} (${top[1]}/${data.model_failures}, ${topPct}%).`
                })()}
              </p>
            </section>
          ) : null}

          {(() => {
            const ft = data.failure_type_counts
            const noFail = ft['NO_FAILURE'] ?? 0
            const retrievalMiss = (ft['RETRIEVAL_MISS'] ?? 0) + (ft['RETRIEVAL_PARTIAL'] ?? 0)
            const llmRuns = data.evaluator_counts.llm_runs
            if (llmRuns < DASHBOARD_LLM_SPARSE_GATE_RUNS) {
              return llmRuns > 0 ? (
                <section className="cl-card" aria-label="LLM evaluation insight" data-testid="dashboard-llm-eval-insight">
                  <h3>LLM Evaluation Insight</h3>
                  <p className="cl-msg cl-msg-warn" role="alert">
                    Sparse sample ({llmRuns} run{llmRuns === 1 ? '' : 's'}) — not reliable
                  </p>
                </section>
              ) : null
            }
            const insightText =
              noFail > 0 && retrievalMiss > 0
                ? 'LLM evaluation captures both successful grounded responses and retrieval failures. When retrieval succeeds, answers are complete and grounded. When context is missing, the model correctly abstains instead of hallucinating.'
                : noFail > 0
                  ? 'LLM evaluation shows consistently grounded responses on retrieved context.'
                  : retrievalMiss > 0
                    ? 'LLM evaluation indicates systemic retrieval or context issues preventing correct answers.'
                    : null
            if (!insightText) return null
            return (
              <section className="cl-card" aria-label="LLM evaluation insight" data-testid="dashboard-llm-eval-insight">
                <h3>LLM Evaluation Insight</h3>
                {llmRuns < 10 ? (
                  <p className="cl-msg cl-msg-info" role="note" data-testid="dashboard-llm-eval-limited">
                    Limited evidence ({llmRuns} runs) — directional only.
                  </p>
                ) : null}
                <p className="cl-dash-llm-insight-text" data-testid="dashboard-llm-eval-insight-text">
                  {insightText}
                </p>
              </section>
            )
          })()}

          <DashboardTrendPanel
            isRefreshing={loading && analytics != null}
            timeSeries={analytics?.time_series ?? []}
            datasetSummary={datasetSummary}
          />

          <section className="cl-card" aria-label="Latency">
            <h2>Latency</h2>
            <p className="cl-muted">
              From persisted <code>runs.*_latency_ms</code> (PostgreSQL <code>percentile_cont</code> for P50/P95).
              End-to-end seconds use the same non-null <code>runs.total_latency_ms</code> slice; seconds = ms ÷
              1000. Latency in local experiments is <strong>directional</strong> (cold-start outliers); not a tight
              SLA or a benchmark score.
            </p>
            <p className="cl-muted cl-latency-median-note" data-testid="dashboard-latency-median-note">
              Median is more representative than average when cold-start outliers are present.
            </p>
            <dl className="cl-dash-dl">
              <div className="cl-dash-dl-row" data-testid="dashboard-retrieval-latency">
                <dt>Retrieval</dt>
                <dd>
                  <ul className="cl-dash-latency-breakdown">
                    <li>
                      <span className="cl-dash-latency-label">Median (P50)</span>{' '}
                      {formatLatencyMs(data.latency.retrieval_latency_p50_ms)}
                    </li>
                    <li>
                      <span className="cl-dash-latency-label">P95</span>{' '}
                      {formatLatencyMs(data.latency.retrieval_latency_p95_ms)}
                    </li>
                    <li className="cl-dash-latency-mean-secondary">
                      <span className="cl-dash-latency-label">Mean</span>{' '}
                      {formatLatencyMs(data.latency.avg_retrieval_latency_ms)}
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
                      <span className="cl-dash-latency-label">Median (P50)</span>{' '}
                      {formatLatencyMs(data.latency.total_latency_p50_ms)}
                      <span className="cl-muted"> · </span>
                      <span className="cl-dash-latency-label">P50 (s)</span>{' '}
                      {formatLatencySec(data.latency.end_to_end_run_latency_p50_sec)}
                    </li>
                    <li>
                      <span className="cl-dash-latency-label">P95</span>{' '}
                      {formatLatencyMs(
                        data.latency.end_to_end_run_latency_p95_sec != null
                          ? data.latency.end_to_end_run_latency_p95_sec * 1000
                          : null,
                      )}
                      <span className="cl-muted"> · </span>
                      <span className="cl-dash-latency-label">P95 (s)</span>{' '}
                      {formatLatencySec(data.latency.end_to_end_run_latency_p95_sec)}
                    </li>
                    <li className="cl-dash-latency-mean-secondary">
                      <span className="cl-dash-latency-label">Mean (ms)</span>{' '}
                      {formatLatencyMs(data.latency.avg_total_latency_ms)}
                    </li>
                    <li className="cl-dash-latency-mean-secondary">
                      <span className="cl-dash-latency-label">Mean (s)</span>{' '}
                      {formatLatencySec(data.latency.end_to_end_run_latency_avg_sec)}
                    </li>
                  </ul>
                </dd>
              </div>
            </dl>
          </section>

          <section className="cl-card" aria-label="Cost summary">
            <h2>LLM cost (evaluation rows)</h2>
            {data.evaluator_counts.llm_runs < DASHBOARD_LLM_SPARSE_GATE_RUNS ? (
              data.evaluator_counts.llm_runs > 0 ? (
                <p className="cl-msg cl-msg-warn" data-testid="dashboard-llm-cost-sparse-gate" role="alert">
                  ⚠ Sparse sample ({data.evaluator_counts.llm_runs} run
                  {data.evaluator_counts.llm_runs === 1 ? '' : 's'}) — not reliable
                </p>
              ) : (
                <p className="cl-muted">No LLM-bucket evaluation runs in this scope.</p>
              )
            ) : (
              <>
                {data.evaluator_counts.llm_runs < 10 ? (
                  <p className="cl-msg cl-msg-info" role="note">
                    LLM evidence is limited; treat cost averages as illustrative, not conclusive.
                  </p>
                ) : null}
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
              </>
            )}
          </section>

          <section className="cl-card" aria-label="Failure types">
            <h2>Failure types (evaluation labels)</h2>
            <p className="cl-muted">
              Counts from <code>evaluation_results.failure_type</code> on organic runs — not the same as{' '}
              <strong>System failures</strong> above.
            </p>
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
                      <th>Eval failure</th>
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
              <ConfigInsightsBucketSection
                heuristic={analytics.config_insights.heuristic}
                llm={analytics.config_insights.llm}
                llmEvalRunCount={data.evaluator_counts.llm_runs}
              />
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
                <CompareBucketsTable result={compare} llmEvalRunCount={data.evaluator_counts.llm_runs} />
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
