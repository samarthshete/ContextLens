import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import type {
  ConfigComparisonMetrics,
  Dataset,
  DocumentListItem,
  DocumentResponse,
  PipelineConfig,
  QueryCase,
  RunDetail,
  RunListItem,
} from '../api/types'
import { describeApiError } from './errorMessage'
import { isBenchmarkFormReady } from './formValidation'
import { UploadDocumentPanel } from './UploadDocumentPanel'
import './benchmark.css'

type View = 'run' | 'runs' | 'detail' | 'compare'

const RUNS_PAGE = 25

function formatJson(v: unknown): string {
  return JSON.stringify(v, null, 2)
}

function formatWhen(iso: string): string {
  try {
    return new Date(iso).toLocaleString()
  } catch {
    return iso
  }
}

const RUN_STATUSES = new Set([
  'pending',
  'running',
  'retrieval_completed',
  'generation_completed',
  'completed',
  'failed',
])

function runStageLabel(status: string): string {
  switch (status) {
    case 'pending':
      return 'Queued'
    case 'running':
      return 'Retrieving…'
    case 'retrieval_completed':
      return 'Generating answer…'
    case 'generation_completed':
      return 'Running LLM judge…'
    case 'completed':
      return 'Finished'
    case 'failed':
      return 'Failed'
    default:
      return status
  }
}

function RunStatusBadge({ status }: { status: string }) {
  const normalized = RUN_STATUSES.has(status) ? status : 'pending'
  const cls = `cl-run-badge cl-run-badge--${normalized.replace(/_/g, '-')}`
  return (
    <span className={cls} title={status}>
      {status.replace(/_/g, ' ')}
    </span>
  )
}

function pipelineLabel(id: number, configs: PipelineConfig[]): string {
  const p = configs.find((c) => c.id === id)
  return p ? `${p.name} (#${id})` : `config #${id}`
}

function EvaluationStructured({ ev }: { ev: Record<string, unknown> | null }) {
  if (!ev || typeof ev !== 'object') {
    return <p className="cl-muted">No evaluation row.</p>
  }
  const faithfulness = ev.faithfulness
  const completeness = ev.completeness
  const retrieval_relevance = ev.retrieval_relevance
  const context_coverage = ev.context_coverage
  const groundedness = ev.groundedness
  const failure_type = ev.failure_type
  const used_llm_judge = ev.used_llm_judge
  const cost_usd = ev.cost_usd
  const meta = ev.metadata_json as Record<string, unknown> | null | undefined

  return (
    <div className="cl-eval-grid">
      <div className="cl-eval-row">
        <span className="cl-eval-k">Faithfulness</span>
        <span>{faithfulness != null ? String(faithfulness) : '—'}</span>
      </div>
      <div className="cl-eval-row">
        <span className="cl-eval-k">Completeness</span>
        <span>{completeness != null ? String(completeness) : '—'}</span>
      </div>
      <div className="cl-eval-row">
        <span className="cl-eval-k">Retrieval relevance</span>
        <span>{retrieval_relevance != null ? String(retrieval_relevance) : '—'}</span>
      </div>
      <div className="cl-eval-row">
        <span className="cl-eval-k">Context coverage</span>
        <span>{context_coverage != null ? String(context_coverage) : '—'}</span>
      </div>
      <div className="cl-eval-row">
        <span className="cl-eval-k">Groundedness</span>
        <span>{groundedness != null ? String(groundedness) : '—'}</span>
      </div>
      <div className="cl-eval-row">
        <span className="cl-eval-k">Failure type</span>
        <span>
          <strong>{failure_type != null ? String(failure_type) : '—'}</strong>
        </span>
      </div>
      <div className="cl-eval-row">
        <span className="cl-eval-k">LLM judge</span>
        <span>{used_llm_judge === true ? 'yes' : used_llm_judge === false ? 'no' : '—'}</span>
      </div>
      <div className="cl-eval-row">
        <span className="cl-eval-k">Est. cost USD</span>
        <span>{cost_usd != null ? String(cost_usd) : '—'}</span>
      </div>
      {meta && Object.keys(meta).length > 0 ? (
        <details className="cl-details">
          <summary>Judge &amp; parse metadata</summary>
          <dl className="cl-meta-dl">
            {Object.entries(meta).map(([k, v]) => (
              <div key={k}>
                <dt>{k}</dt>
                <dd>{typeof v === 'object' ? formatJson(v) : String(v)}</dd>
              </div>
            ))}
          </dl>
        </details>
      ) : null}
    </div>
  )
}

function MetricsTable({ rows, title }: { rows: ConfigComparisonMetrics[]; title: string }) {
  if (!rows.length) {
    return (
      <div className="cl-card cl-empty">
        <p className="cl-muted">
          No traced runs for <strong>{title}</strong> (empty bucket or no data).
        </p>
      </div>
    )
  }
  return (
    <div className="cl-card">
      <h2>{title}</h2>
      <div className="cl-table-wrap">
        <table className="cl-table">
          <thead>
            <tr>
              <th>Config</th>
              <th>Traced</th>
              <th>Avg ret. ms</th>
              <th>Avg eval ms</th>
              <th>Avg total ms</th>
              <th>Avg rel.</th>
              <th>Failure counts</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((m) => {
              const fc = m.failure_type_counts || {}
              const failStr =
                Object.keys(fc).length === 0
                  ? '—'
                  : Object.entries(fc)
                      .map(([k, v]) => `${k}: ${v}`)
                      .join('; ')
              return (
                <tr key={m.pipeline_config_id}>
                  <td>{m.pipeline_config_id}</td>
                  <td>{m.traced_runs}</td>
                  <td>{m.avg_retrieval_latency_ms?.toFixed?.(1) ?? '—'}</td>
                  <td>{m.avg_evaluation_latency_ms?.toFixed?.(1) ?? '—'}</td>
                  <td>{m.avg_total_latency_ms?.toFixed?.(1) ?? '—'}</td>
                  <td>{m.avg_retrieval_relevance?.toFixed?.(3) ?? '—'}</td>
                  <td className="cl-td-wrap">{failStr}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export function BenchmarkWorkspace() {
  const [view, setView] = useState<View>('run')
  const [datasets, setDatasets] = useState<Dataset[]>([])
  const [queryCases, setQueryCases] = useState<QueryCase[]>([])
  const [pipelineConfigs, setPipelineConfigs] = useState<PipelineConfig[]>([])
  const [documents, setDocuments] = useState<DocumentListItem[]>([])

  const [datasetId, setDatasetId] = useState<number | ''>('')
  const [queryCaseId, setQueryCaseId] = useState<number | ''>('')
  const [pipelineConfigId, setPipelineConfigId] = useState<number | ''>('')
  const [documentId, setDocumentId] = useState<number | '' | 'none'>('none')
  const [evalMode, setEvalMode] = useState<'heuristic' | 'full'>('heuristic')

  const [registryLoading, setRegistryLoading] = useState(true)
  const [queryCasesLoading, setQueryCasesLoading] = useState(false)
  const [submitLoading, setSubmitLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [successMsg, setSuccessMsg] = useState<string | null>(null)
  const [lastRunId, setLastRunId] = useState<number | null>(null)
  /** Full-mode: poll until ``completed`` / ``failed``. */
  const [pollingRunId, setPollingRunId] = useState<number | null>(null)
  const [longRunHint, setLongRunHint] = useState(false)
  const pollStartedAtRef = useRef<number | null>(null)

  const [runs, setRuns] = useState<RunListItem[]>([])
  const [runsTotal, setRunsTotal] = useState(0)
  const [runsHasMore, setRunsHasMore] = useState(false)
  const [runsLoading, setRunsLoading] = useState(false)
  /** Next offset for “Load more” (ref avoids stale closures). */
  const runsNextOffsetRef = useRef(0)

  const [detailRunId, setDetailRunId] = useState<number | null>(null)
  const [runDetail, setRunDetail] = useState<RunDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)

  const [compareSelected, setCompareSelected] = useState<Set<number>>(new Set())
  const [compareEvaluator, setCompareEvaluator] = useState<'heuristic' | 'llm' | 'both'>('both')
  const [compareCombine, setCompareCombine] = useState(false)
  const [compareLoading, setCompareLoading] = useState(false)
  const [compareResult, setCompareResult] = useState<Awaited<
    ReturnType<typeof api.configComparison>
  > | null>(null)

  const canSubmit = isBenchmarkFormReady(datasetId, queryCaseId, pipelineConfigId)

  const clearMessages = useCallback(() => {
    setError(null)
    setSuccessMsg(null)
  }, [])

  const loadRegistry = useCallback(async () => {
    setRegistryLoading(true)
    clearMessages()
    try {
      const [ds, pcs, docs] = await Promise.all([
        api.listDatasets(),
        api.listPipelineConfigs(),
        api.listDocuments(),
      ])
      setDatasets(ds)
      setPipelineConfigs(pcs)
      setDocuments(docs)
    } catch (e) {
      setError(describeApiError(e))
    } finally {
      setRegistryLoading(false)
    }
  }, [clearMessages])

  const refreshDocumentsOnly = useCallback(async () => {
    try {
      const docs = await api.listDocuments()
      setDocuments(docs)
    } catch (e) {
      setError(describeApiError(e))
    }
  }, [])

  const handleDocumentUploaded = useCallback(
    async (doc: DocumentResponse) => {
      await refreshDocumentsOnly()
      setDocumentId(doc.id)
      setError(null)
    },
    [refreshDocumentsOnly],
  )

  useEffect(() => {
    void loadRegistry()
  }, [loadRegistry])

  useEffect(() => {
    if (datasetId === '') {
      setQueryCases([])
      setQueryCaseId('')
      setQueryCasesLoading(false)
      return
    }
    let cancelled = false
    setQueryCasesLoading(true)
    clearMessages()
    ;(async () => {
      try {
        const qc = await api.listQueryCases(Number(datasetId))
        if (!cancelled) {
          setQueryCases(qc)
          setQueryCaseId((prev) => {
            if (qc.length === 0) return ''
            if (prev === '') return qc[0].id
            const ok = qc.some((q) => q.id === prev)
            return ok ? prev : qc[0].id
          })
        }
      } catch (e) {
        if (!cancelled) {
          setQueryCases([])
          setQueryCaseId('')
          setError(describeApiError(e))
        }
      } finally {
        if (!cancelled) setQueryCasesLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [datasetId, clearMessages])

  const refreshRuns = useCallback(async (opts?: { quiet?: boolean }) => {
    setRunsLoading(true)
    try {
      const r = await api.listRuns({ limit: RUNS_PAGE, offset: 0 })
      setRuns(r.items)
      runsNextOffsetRef.current = r.items.length
      setRunsTotal(r.total)
      setRunsHasMore(r.items.length < r.total)
    } catch (e) {
      if (!opts?.quiet) setError(describeApiError(e))
    } finally {
      setRunsLoading(false)
    }
  }, [])

  const loadMoreRuns = useCallback(async () => {
    setRunsLoading(true)
    try {
      const offset = runsNextOffsetRef.current
      const r = await api.listRuns({ limit: RUNS_PAGE, offset })
      setRuns((prev) => [...prev, ...r.items])
      runsNextOffsetRef.current = offset + r.items.length
      setRunsTotal(r.total)
      setRunsHasMore(runsNextOffsetRef.current < r.total)
    } catch (e) {
      setError(describeApiError(e))
    } finally {
      setRunsLoading(false)
    }
  }, [])

  useEffect(() => {
    if (view === 'runs') {
      void refreshRuns()
    }
  }, [view, refreshRuns])

  useEffect(() => {
    if (view !== 'detail' || detailRunId == null) {
      setRunDetail(null)
      setDetailLoading(false)
      return
    }
    let cancelled = false
    setDetailLoading(true)
    clearMessages()
    ;(async () => {
      try {
        const d = await api.getRun(detailRunId)
        if (!cancelled) setRunDetail(d)
      } catch (e) {
        if (!cancelled) {
          setRunDetail(null)
          setError(describeApiError(e))
        }
      } finally {
        if (!cancelled) setDetailLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [view, detailRunId, clearMessages])

  useEffect(() => {
    if (pollingRunId == null) {
      pollStartedAtRef.current = null
      setLongRunHint(false)
      return
    }
    let cancelled = false
    const pollOnce = async () => {
      try {
        const d = await api.getRun(pollingRunId)
        if (cancelled) return
        if (detailRunId === pollingRunId) {
          setRunDetail(d)
          setDetailLoading(false)
        }
        void refreshRuns({ quiet: true })
        const start = pollStartedAtRef.current
        setLongRunHint(start != null && Date.now() - start > 45_000)
        if (d.status === 'completed' || d.status === 'failed') {
          setPollingRunId(null)
          pollStartedAtRef.current = null
          setLongRunHint(false)
          if (d.status === 'failed') {
            setSuccessMsg(null)
            setError(`Run #${d.run_id} failed. Open detail or Recent runs for status.`)
          } else {
            setError(null)
            setSuccessMsg(`Run #${d.run_id} completed.`)
          }
        }
      } catch (e) {
        if (!cancelled) setError(describeApiError(e))
      }
    }
    void pollOnce()
    const iv = window.setInterval(() => void pollOnce(), 3000)
    return () => {
      cancelled = true
      window.clearInterval(iv)
    }
  }, [pollingRunId, detailRunId, refreshRuns])

  function goView(next: View) {
    clearMessages()
    setView(next)
    if (next === 'detail' && detailRunId == null && lastRunId != null) {
      setDetailRunId(lastRunId)
    }
  }

  async function handleSubmitRun(e: React.FormEvent) {
    e.preventDefault()
    if (!canSubmit) return
    setSubmitLoading(true)
    clearMessages()
    try {
      const body = {
        query_case_id: Number(queryCaseId),
        pipeline_config_id: Number(pipelineConfigId),
        eval_mode: evalMode,
        document_id:
          documentId === 'none' || documentId === '' ? undefined : Number(documentId),
      }
      const res = await api.createRun(body)
      setLastRunId(res.run_id)
      setDetailRunId(res.run_id)
      if (res.httpStatus === 202) {
        const jobHint =
          res.job_id != null && res.job_id !== ''
            ? ` Job id: ${res.job_id}.`
            : ''
        setSuccessMsg(`Run started. Status updates every few seconds.${jobHint}`)
        setPollingRunId(res.run_id)
        pollStartedAtRef.current = Date.now()
        setLongRunHint(false)
      } else {
        setPollingRunId(null)
        pollStartedAtRef.current = null
        setLongRunHint(false)
        setSuccessMsg(`Run #${res.run_id} completed with status “${res.status}”.`)
      }
      void refreshRuns({ quiet: res.httpStatus === 202 })
      setView('detail')
    } catch (err) {
      setError(describeApiError(err))
    } finally {
      setSubmitLoading(false)
    }
  }

  async function handleCompare() {
    const ids = [...compareSelected].sort((a, b) => a - b)
    if (ids.length < 1) {
      setError('Select at least one pipeline config to compare.')
      return
    }
    setCompareLoading(true)
    clearMessages()
    try {
      const r = await api.configComparison(ids, {
        evaluatorType: compareEvaluator,
        combineEvaluators: compareCombine,
      })
      setCompareResult(r)
    } catch (err) {
      setCompareResult(null)
      setError(describeApiError(err))
    } finally {
      setCompareLoading(false)
    }
  }

  function toggleCompare(id: number) {
    setCompareSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  return (
    <div className="cl-app">
      <header className="cl-header">
        <h1>ContextLens — Benchmark</h1>
        <nav className="cl-nav" aria-label="Main">
          <button type="button" data-active={view === 'run'} onClick={() => goView('run')}>
            Run benchmark
          </button>
          <button type="button" data-active={view === 'runs'} onClick={() => goView('runs')}>
            Recent runs
          </button>
          <button type="button" data-active={view === 'detail'} onClick={() => goView('detail')}>
            Run detail
          </button>
          <button type="button" data-active={view === 'compare'} onClick={() => goView('compare')}>
            Config comparison
          </button>
        </nav>
      </header>

      {registryLoading && view === 'run' ? (
        <p className="cl-loading" aria-live="polite">
          Loading registry…
        </p>
      ) : null}

      {error ? (
        <div className="cl-msg cl-msg-error" role="alert">
          {error}
        </div>
      ) : null}

      {successMsg ? (
        <div className="cl-msg cl-msg-ok" role="status">
          {successMsg}
        </div>
      ) : null}

      {pollingRunId != null && longRunHint ? (
        <div className="cl-msg cl-msg-info" role="status">
          Still running… this may take a while
        </div>
      ) : null}

      {view === 'run' && (
        <form className="cl-card" onSubmit={handleSubmitRun}>
          <h2>New traced run</h2>
          <p className="cl-muted">
            Backend <code>POST /api/v1/runs</code> · Vite proxies <code>/api</code> (default backend{' '}
            <code>:8002</code>).
          </p>

          {!datasets.length && !registryLoading ? (
            <p className="cl-empty-banner">
              No datasets found. Seed the benchmark registry (<code>seed_benchmark.py</code>) or add rows
              via scripts.
            </p>
          ) : null}

          <div className="cl-field">
            <label htmlFor="dataset">Dataset</label>
            <select
              id="dataset"
              value={datasetId === '' ? '' : String(datasetId)}
              onChange={(ev) => {
                const v = ev.target.value
                setDatasetId(v === '' ? '' : Number(v))
                setQueryCaseId('')
              }}
              disabled={registryLoading}
            >
              <option value="">Select dataset…</option>
              {datasets.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name} (id {d.id})
                </option>
              ))}
            </select>
          </div>

          <div className="cl-field">
            <label htmlFor="qc">Query case</label>
            {queryCasesLoading ? (
              <p className="cl-loading-inline">Loading query cases…</p>
            ) : (
              <select
                id="qc"
                value={queryCaseId === '' ? '' : String(queryCaseId)}
                onChange={(ev) => {
                  const v = ev.target.value
                  setQueryCaseId(v === '' ? '' : Number(v))
                }}
                disabled={datasetId === '' || !queryCases.length}
              >
                <option value="">
                  {datasetId === '' ? 'Select a dataset first' : 'Select query case…'}
                </option>
                {queryCases.map((q) => (
                  <option key={q.id} value={q.id}>
                    {q.query_text.slice(0, 72)}
                    {q.query_text.length > 72 ? '…' : ''} (id {q.id})
                  </option>
                ))}
              </select>
            )}
          </div>

          <div className="cl-field">
            <label htmlFor="pc">Pipeline config</label>
            <select
              id="pc"
              value={pipelineConfigId === '' ? '' : String(pipelineConfigId)}
              onChange={(ev) => {
                const v = ev.target.value
                setPipelineConfigId(v === '' ? '' : Number(v))
              }}
              disabled={registryLoading || !pipelineConfigs.length}
            >
              <option value="">Select pipeline config…</option>
              {pipelineConfigs.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name} — top_k {p.top_k} (id {p.id})
                </option>
              ))}
            </select>
          </div>

          <div className="cl-field">
            <label htmlFor="doc">Document scope (optional)</label>
            <select
              id="doc"
              value={documentId === 'none' ? 'none' : String(documentId)}
              onChange={(ev) => {
                const v = ev.target.value
                setDocumentId(v === 'none' ? 'none' : Number(v))
              }}
              disabled={registryLoading}
            >
              <option value="none">All indexed chunks (no filter)</option>
              {documents.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.title} — {d.status} (id {d.id})
                </option>
              ))}
            </select>
          </div>

          <UploadDocumentPanel
            disabled={registryLoading}
            onDocumentUploaded={(doc) => void handleDocumentUploaded(doc)}
          />

          <div className="cl-field">
            <label htmlFor="eval">Eval mode</label>
            <select
              id="eval"
              value={evalMode}
              onChange={(ev) => setEvalMode(ev.target.value as 'heuristic' | 'full')}
            >
              <option value="heuristic">heuristic (no Claude)</option>
              <option value="full">full (generation + judge — needs API key)</option>
            </select>
          </div>

          {!canSubmit && !registryLoading ? (
            <p className="cl-hint">Select dataset, query case, and pipeline config to enable Run.</p>
          ) : null}

          <div className="cl-actions">
            <button type="submit" className="cl-btn" disabled={!canSubmit || submitLoading || registryLoading}>
              {submitLoading
                ? evalMode === 'full'
                  ? 'Starting…'
                  : 'Running…'
                : evalMode === 'full'
                  ? 'Start full run'
                  : 'Run benchmark'}
            </button>
            <button
              type="button"
              className="cl-btn cl-btn-secondary"
              disabled={registryLoading}
              onClick={() => void loadRegistry()}
            >
              Reload registry
            </button>
          </div>
        </form>
      )}

      {view === 'runs' && (
        <section className="cl-card">
          <h2>Recent runs</h2>
          <p className="cl-muted">
            Showing {runs.length} of {runsTotal} · newest first
          </p>
          <div className="cl-actions" style={{ marginTop: 0 }}>
            <button
              type="button"
              className="cl-btn cl-btn-secondary"
              disabled={runsLoading}
              onClick={() => {
                clearMessages()
                void refreshRuns()
              }}
            >
              {runsLoading ? 'Loading…' : 'Refresh'}
            </button>
          </div>
          {runsLoading && !runs.length ? (
            <p className="cl-loading">Loading runs…</p>
          ) : !runs.length ? (
            <p className="cl-empty-banner">No runs yet. Create one from “Run benchmark”.</p>
          ) : (
            <div className="cl-table-wrap">
              <table className="cl-table">
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>Created</th>
                    <th>Status</th>
                    <th>Pipeline</th>
                    <th>Query</th>
                    <th>Evaluator</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {runs.map((r) => (
                    <tr key={r.run_id}>
                      <td>{r.run_id}</td>
                      <td>{formatWhen(r.created_at)}</td>
                      <td>
                        <RunStatusBadge status={r.status} />
                      </td>
                      <td>{pipelineLabel(r.pipeline_config_id, pipelineConfigs)}</td>
                      <td>
                        {r.query_text.slice(0, 40)}
                        {r.query_text.length > 40 ? '…' : ''}
                      </td>
                      <td>{r.evaluator_type}</td>
                      <td>
                        <button
                          type="button"
                          className="link"
                          onClick={() => {
                            setDetailRunId(r.run_id)
                            clearMessages()
                            setView('detail')
                          }}
                        >
                          Open
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {runsHasMore ? (
            <div className="cl-actions">
              <button
                type="button"
                className="cl-btn cl-btn-secondary"
                disabled={runsLoading}
                onClick={() => void loadMoreRuns()}
              >
                {runsLoading ? 'Loading…' : 'Load more'}
              </button>
            </div>
          ) : null}
        </section>
      )}

      {view === 'detail' && (
        <section className="cl-card">
          <h2>Run detail</h2>
          <div className="cl-field">
            <label htmlFor="rid">Run ID</label>
            <input
              id="rid"
              type="text"
              inputMode="numeric"
              placeholder="e.g. 42"
              value={detailRunId ?? ''}
              onChange={(ev) => {
                const t = ev.target.value.trim()
                if (t === '') {
                  setDetailRunId(null)
                  return
                }
                const n = Number(t)
                setDetailRunId(Number.isFinite(n) ? n : null)
              }}
            />
          </div>
          {detailLoading ? (
            <p className="cl-loading">Loading run…</p>
          ) : runDetail ? (
            <>
              <section className="cl-subsection">
                <h3>Summary</h3>
                <p className="cl-muted cl-detail-status-row">
                  <RunStatusBadge status={runDetail.status} />
                  <span className="cl-stage-label">
                    Stage: <strong>{runStageLabel(runDetail.status)}</strong>
                  </span>
                  {runDetail.status !== 'completed' && runDetail.status !== 'failed' ? (
                    <span className="cl-pulse" aria-live="polite">
                      Updating…
                    </span>
                  ) : null}
                </p>
                <p className="cl-muted">
                  Evaluator <strong>{runDetail.evaluator_type}</strong> · created{' '}
                  {formatWhen(runDetail.created_at)}
                </p>
                <p className="cl-muted">
                  Latencies (ms) — retrieval / generation / evaluation / total:{' '}
                  {runDetail.retrieval_latency_ms ?? '—'} / {runDetail.generation_latency_ms ?? '—'} /{' '}
                  {runDetail.evaluation_latency_ms ?? '—'} / {runDetail.total_latency_ms ?? '—'}
                </p>
              </section>

              <section className="cl-subsection">
                <h3>Query</h3>
                <p>{runDetail.query_case.query_text}</p>
                {runDetail.query_case.expected_answer ? (
                  <p className="cl-muted">
                    <em>Expected:</em> {runDetail.query_case.expected_answer}
                  </p>
                ) : null}
              </section>

              <section className="cl-subsection">
                <h3>Pipeline config</h3>
                <p>
                  <strong>{runDetail.pipeline_config.name}</strong> (id {runDetail.pipeline_config.id}) ·{' '}
                  {runDetail.pipeline_config.embedding_model} · {runDetail.pipeline_config.chunk_strategy} ·
                  top_k {runDetail.pipeline_config.top_k}
                </p>
              </section>

              <section className="cl-subsection">
                <h3>Retrieval hits ({runDetail.retrieval_hits.length})</h3>
                {!runDetail.retrieval_hits.length ? (
                  <p className="cl-muted">No chunks retrieved.</p>
                ) : (
                  runDetail.retrieval_hits.map((h) => (
                    <div key={h.chunk_id} className="cl-hit">
                      <strong>#{h.rank}</strong> score {h.score.toFixed(4)} · doc {h.document_id} · chunk{' '}
                      {h.chunk_id}
                      <pre className="cl-pre cl-pre-sm">{h.content}</pre>
                    </div>
                  ))
                )}
              </section>

              <section className="cl-subsection">
                <h3>Generation</h3>
                {runDetail.generation && typeof runDetail.generation.answer_text === 'string' ? (
                  <pre className="cl-pre">{String(runDetail.generation.answer_text)}</pre>
                ) : runDetail.generation ? (
                  <details className="cl-details">
                    <summary>Raw generation JSON</summary>
                    <pre className="cl-pre">{formatJson(runDetail.generation)}</pre>
                  </details>
                ) : (
                  <p className="cl-muted">No generation (heuristic path).</p>
                )}
              </section>

              <section className="cl-subsection">
                <h3>Evaluation</h3>
                <EvaluationStructured ev={runDetail.evaluation} />
                <details className="cl-details">
                  <summary>Raw evaluation JSON (debug)</summary>
                  <pre className="cl-pre">{formatJson(runDetail.evaluation)}</pre>
                </details>
              </section>
            </>
          ) : (
            <p className="cl-muted">Enter a run id or open a row from “Recent runs”.</p>
          )}
        </section>
      )}

      {view === 'compare' && (
        <section>
          <div className="cl-card">
            <h2>Config comparison</h2>
            <p className="cl-muted">
              Uses <code>GET /runs/config-comparison</code>. Heuristic vs LLM buckets stay separate unless you
              enable “Combine evaluators”.
            </p>

            {registryLoading ? (
              <p className="cl-loading">Loading pipeline configs…</p>
            ) : null}

            {!pipelineConfigs.length && !registryLoading ? (
              <p className="cl-empty-banner">No pipeline configs loaded. Reload registry from “Run benchmark”.</p>
            ) : null}

            <div className="cl-field">
              <label htmlFor="cev">Evaluator slice</label>
              <select
                id="cev"
                value={compareEvaluator}
                onChange={(ev) =>
                  setCompareEvaluator(ev.target.value as 'heuristic' | 'llm' | 'both')
                }
              >
                <option value="both">Both (separate tables: heuristic + LLM)</option>
                <option value="heuristic">Heuristic only</option>
                <option value="llm">LLM only</option>
              </select>
            </div>

            <div className="cl-check">
              <input
                type="checkbox"
                id="ccomb"
                checked={compareCombine}
                onChange={(ev) => setCompareCombine(ev.target.checked)}
              />
              <label htmlFor="ccomb">
                Combine evaluators (single merged row per config —{' '}
                <code>combine_evaluators=true</code>)
              </label>
            </div>

            <h3 className="cl-h3-muted">Pipeline configs</h3>
            {pipelineConfigs.map((p) => (
              <div key={p.id} className="cl-check">
                <input
                  type="checkbox"
                  id={`cmp-${p.id}`}
                  checked={compareSelected.has(p.id)}
                  onChange={() => toggleCompare(p.id)}
                />
                <label htmlFor={`cmp-${p.id}`}>
                  {p.name} (id {p.id}) — top_k {p.top_k}
                </label>
              </div>
            ))}

            <div className="cl-actions">
              <button
                type="button"
                className="cl-btn"
                disabled={compareLoading || !compareSelected.size}
                onClick={() => void handleCompare()}
              >
                {compareLoading ? 'Loading…' : 'Compare'}
              </button>
              <button
                type="button"
                className="cl-btn cl-btn-secondary"
                disabled={registryLoading}
                onClick={() => void loadRegistry()}
              >
                Reload configs
              </button>
            </div>
          </div>

          {compareResult?.buckets ? (
            <div className="cl-compare-grid">
              <MetricsTable rows={compareResult.buckets.heuristic ?? []} title="Heuristic bucket" />
              <MetricsTable rows={compareResult.buckets.llm ?? []} title="LLM bucket" />
            </div>
          ) : compareResult?.configs ? (
            <MetricsTable rows={compareResult.configs} title="Combined (heuristic + LLM merged)" />
          ) : (
            <p className="cl-muted cl-card cl-empty">Run Compare to load aggregates.</p>
          )}
        </section>
      )}
    </div>
  )
}
