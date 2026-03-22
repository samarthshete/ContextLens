import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
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
import { RegistryPanel, type RegistryNotice } from './RegistryPanel'
import { RunQueuePanel } from './RunQueuePanel'
import { UploadDocumentPanel } from './UploadDocumentPanel'
import { DashboardPanel } from './DashboardPanel'
import { ContextQualityPanel } from './ContextQualityPanel'
import { GenerationJudgeInsightsPanel } from './GenerationJudgeInsightsPanel'
import { RunDiffPanel } from './RunDiffPanel'
import { documentTitleLookupMap } from './retrievalSourceFormat'
import { RetrievalHitsSection } from './RetrievalHitsSection'
import { RetrievalDiagnosisPanel } from './RetrievalDiagnosisPanel'
import { RunDiagnosisSummary } from './RunDiagnosisSummary'
import { DocumentDetailPanel } from './DocumentDetailPanel'
import { PhaseTimeline } from './PhaseTimeline'
import { QueueBrowserPanel } from './QueueBrowserPanel'
import { RunsFilterBar } from './RunsFilterBar'
import {
  RUNS_LIST_FILTERS_INIT,
  buildListRunsApiParams,
  narrowRunsOnPage,
  type RunsListServerFilters,
} from './runsListQuery'
import {
  runTraceExportFilename,
  serializeRunTraceJson,
  triggerBrowserDownload,
} from './exportDownload'
import './benchmark.css'

export type View = 'run' | 'runs' | 'queue' | 'detail' | 'compare' | 'dashboard' | 'document'

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

export function BenchmarkWorkspace({ routeView }: { routeView: View }) {
  const navigate = useNavigate()
  const params = useParams<{ runId?: string; documentId?: string }>()
  const view = routeView
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
  const [registryInitDone, setRegistryInitDone] = useState(false)
  const [registryNotice, setRegistryNotice] = useState<RegistryNotice | null>(null)
  const selectionRef = useRef({
    datasetId: '' as number | '',
    queryCaseId: '' as number | '',
    pipelineConfigId: '' as number | '',
  })
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
  const [runsFilters, setRunsFilters] = useState<RunsListServerFilters>(RUNS_LIST_FILTERS_INIT)
  const [runsNarrowText, setRunsNarrowText] = useState('')

  // Derive initial detailRunId from URL params when entering via /runs/:runId
  const paramRunId = params.runId != null ? Number(params.runId) : null
  const [detailRunId, setDetailRunId] = useState<number | null>(
    view === 'detail' && paramRunId != null && Number.isFinite(paramRunId) ? paramRunId : null,
  )
  const [runDetail, setRunDetail] = useState<RunDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)

  const [compareSelected, setCompareSelected] = useState<Set<number>>(new Set())
  const [compareEvaluator, setCompareEvaluator] = useState<'heuristic' | 'llm' | 'both'>('both')
  const [compareCombine, setCompareCombine] = useState(false)
  const [compareLoading, setCompareLoading] = useState(false)
  const [compareResult, setCompareResult] = useState<Awaited<
    ReturnType<typeof api.configComparison>
  > | null>(null)

  const dashboardCompareIds = useMemo(
    () => pipelineConfigs.map((c) => c.id).slice(0, 12),
    [pipelineConfigs],
  )

  const documentTitleById = useMemo(() => documentTitleLookupMap(documents), [documents])

  const runsVisible = useMemo(
    () => narrowRunsOnPage(runs, runsNarrowText, pipelineConfigs),
    [runs, runsNarrowText, pipelineConfigs],
  )

  const clearRunsFilters = useCallback(() => {
    setRunsFilters(RUNS_LIST_FILTERS_INIT)
    setRunsNarrowText('')
  }, [])

  // Sync detailRunId from URL when the route param changes
  useEffect(() => {
    if (view === 'detail' && paramRunId != null && Number.isFinite(paramRunId)) {
      setDetailRunId(paramRunId)
    }
  }, [view, paramRunId])

  const canSubmit = isBenchmarkFormReady(datasetId, queryCaseId, pipelineConfigId)

  selectionRef.current = { datasetId, queryCaseId, pipelineConfigId }

  const clearMessages = useCallback(() => {
    setError(null)
    setSuccessMsg(null)
  }, [])

  const loadRegistry = useCallback(
    async (options?: { preserveSelection?: boolean }) => {
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
        setDocumentId((prev) => {
          if (prev === 'none' || prev === '') return prev
          if (docs.some((d) => d.id === prev)) return prev
          return 'none'
        })

        if (options?.preserveSelection) {
          const snap = selectionRef.current
          const nextD =
            snap.datasetId !== '' && ds.some((x) => x.id === snap.datasetId) ? snap.datasetId : ''
          setDatasetId(nextD)
          if (nextD !== '') {
            setQueryCasesLoading(true)
            try {
              const qc = await api.listQueryCases(Number(nextD))
              setQueryCases(qc)
              const nextQ =
                snap.queryCaseId !== '' && qc.some((x) => x.id === snap.queryCaseId)
                  ? snap.queryCaseId
                  : qc.length
                    ? qc[0].id
                    : ''
              setQueryCaseId(nextQ)
            } finally {
              setQueryCasesLoading(false)
            }
          } else {
            setQueryCases([])
            setQueryCaseId('')
          }
          const nextP =
            snap.pipelineConfigId !== '' && pcs.some((x) => x.id === snap.pipelineConfigId)
              ? snap.pipelineConfigId
              : ''
          setPipelineConfigId(nextP)
        }
      } catch (e) {
        setError(describeApiError(e))
      } finally {
        setRegistryLoading(false)
        setRegistryInitDone(true)
      }
    },
    [clearMessages],
  )

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
      const r = await api.listRuns({
        limit: RUNS_PAGE,
        offset: 0,
        ...buildListRunsApiParams(runsFilters),
      })
      setRuns(r.items)
      runsNextOffsetRef.current = r.items.length
      setRunsTotal(r.total)
      setRunsHasMore(r.items.length < r.total)
    } catch (e) {
      if (!opts?.quiet) setError(describeApiError(e))
    } finally {
      setRunsLoading(false)
    }
  }, [runsFilters])

  const loadMoreRuns = useCallback(async () => {
    setRunsLoading(true)
    try {
      const offset = runsNextOffsetRef.current
      const r = await api.listRuns({
        limit: RUNS_PAGE,
        offset,
        ...buildListRunsApiParams(runsFilters),
      })
      setRuns((prev) => [...prev, ...r.items])
      runsNextOffsetRef.current = offset + r.items.length
      setRunsTotal(r.total)
      setRunsHasMore(runsNextOffsetRef.current < r.total)
    } catch (e) {
      setError(describeApiError(e))
    } finally {
      setRunsLoading(false)
    }
  }, [runsFilters])

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
    setRegistryNotice(null)
    if (next === 'detail') {
      const id = detailRunId ?? lastRunId
      if (id != null) {
        navigate(`/runs/${id}`)
      } else {
        navigate('/runs')
      }
      return
    }
    const paths: Record<View, string> = {
      run: '/benchmark',
      runs: '/runs',
      queue: '/queue',
      detail: '/runs',
      compare: '/compare',
      dashboard: '/dashboard',
      document: '/benchmark',
    }
    navigate(paths[next])
  }

  async function handleSubmitRun(e: React.FormEvent) {
    e.preventDefault()
    if (!canSubmit) return
    setSubmitLoading(true)
    clearMessages()
    setRegistryNotice(null)
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
      navigate(`/runs/${res.run_id}`)
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
          <button type="button" data-active={view === 'dashboard'} onClick={() => goView('dashboard')}>
            Dashboard
          </button>
        </nav>
      </header>

      {view === 'run' && !registryInitDone ? (
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

      {view === 'run' && registryInitDone && (
        <>
          <section className="cl-card cl-flow-card" aria-label="Workflow">
            <h2 className="cl-flow-title">How to run a benchmark</h2>
            <ol className="cl-flow-steps">
              <li>
                <strong>Registry</strong> — ensure a dataset, at least one query case, and a pipeline config
                exist (use the section below or <code>seed_benchmark.py</code>).
              </li>
              <li>
                <strong>Corpus scope (optional)</strong> — limit retrieval to one uploaded document, or leave{' '}
                <em>All indexed chunks</em> to search everything.
              </li>
              <li>
                <strong>Eval mode</strong> — heuristic (fast, no LLM generation) or full RAG (OpenAI by default, Redis
                worker, API key).
              </li>
            </ol>
          </section>

          {registryLoading ? (
            <p className="cl-loading-inline cl-flow-refresh" aria-live="polite">
              Refreshing registry lists…
            </p>
          ) : null}

          <RegistryPanel
            datasets={datasets}
            pipelineConfigs={pipelineConfigs}
            selectedDatasetId={datasetId}
            registryLoading={registryLoading}
            onPreservingReload={() => loadRegistry({ preserveSelection: true })}
            notice={registryNotice}
            setNotice={setRegistryNotice}
            onCreatedDataset={(id) => setDatasetId(id)}
            onCreatedQueryCase={(id) => setQueryCaseId(id)}
            onCreatedPipelineConfig={(id) => setPipelineConfigId(id)}
          />

          <form className="cl-card cl-run-form" onSubmit={handleSubmitRun}>
            <h2>Start a run</h2>
            <p className="cl-muted">
              <code>POST /api/v1/runs</code> · Vite proxies <code>/api</code> (default backend <code>:8002</code>).
            </p>

            {!datasets.length && !registryLoading ? (
              <p className="cl-empty-banner">
                No datasets yet. Create one under <strong>Benchmark registry</strong> above or run{' '}
                <code>seed_benchmark.py</code>.
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

          <section className="cl-subcard" aria-labelledby="corpus-heading">
            <h3 id="corpus-heading" className="cl-subcard-title">
              Corpus scope &amp; upload
            </h3>
            <p className="cl-field-hint cl-mb">
              Retrieval always uses your vector index. Choose <strong>All indexed chunks</strong> to search every
              processed document, or pick a single document to scope the run (same as CLI <code>--document-id</code>
              ).
            </p>
            <div className="cl-field">
              <label htmlFor="doc">Document scope for this run</label>
              <select
                id="doc"
                value={documentId === 'none' ? 'none' : String(documentId)}
                onChange={(ev) => {
                  const v = ev.target.value
                  setDocumentId(v === 'none' ? 'none' : Number(v))
                }}
                disabled={registryLoading}
              >
                <option value="none">All indexed chunks (no document filter)</option>
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
          </section>

          <div className="cl-field">
            <label htmlFor="eval">Eval mode</label>
            <select
              id="eval"
              value={evalMode}
              onChange={(ev) => setEvalMode(ev.target.value as 'heuristic' | 'full')}
            >
              <option value="heuristic">heuristic (no LLM generation)</option>
              <option value="full">full (OpenAI generation + judge — needs key + worker)</option>
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
              onClick={() => void loadRegistry({ preserveSelection: true })}
            >
              Reload lists &amp; documents
            </button>
          </div>
        </form>
        </>
      )}

      {view === 'runs' && (
        <section className="cl-card">
          <h2>Recent runs</h2>
          <RunsFilterBar
            values={runsFilters}
            narrowText={runsNarrowText}
            onChange={(partial) => setRunsFilters((prev) => ({ ...prev, ...partial }))}
            onNarrowTextChange={setRunsNarrowText}
            onClear={clearRunsFilters}
            datasets={datasets}
            pipelineConfigs={pipelineConfigs}
          />
          <p className="cl-muted">
            Showing {runsVisible.length} of {runs.length} on this page · {runsTotal} total match current filters
            {runsNarrowText.trim() ? ' (narrow filter active on loaded rows)' : ''} · newest first
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
          ) : runsVisible.length === 0 ? (
            <p className="cl-empty-banner" data-testid="runs-narrow-empty">
              No runs on this page match the narrow filter. Clear it or load more rows.
            </p>
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
                  {runsVisible.map((r) => (
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
                            clearMessages()
                            navigate(`/runs/${r.run_id}`)
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
                  navigate('/runs', { replace: true })
                  return
                }
                const n = Number(t)
                if (Number.isFinite(n) && Number.isInteger(n) && n > 0) {
                  setDetailRunId(n)
                  navigate(`/runs/${n}`, { replace: true })
                } else {
                  setDetailRunId(null)
                }
              }}
            />
          </div>
          {params.runId != null && (detailRunId == null || !Number.isFinite(detailRunId)) ? (
            <p className="cl-msg cl-msg-error" role="alert">
              Invalid run ID: &quot;{params.runId}&quot;. Run IDs must be positive integers.
            </p>
          ) : detailLoading ? (
            <p className="cl-loading">Loading run…</p>
          ) : runDetail ? (
            <>
              <section className="cl-subsection">
                <div className="cl-subsection-header-row">
                  <h3>Summary</h3>
                  <button
                    type="button"
                    className="cl-btn cl-btn-secondary cl-btn-sm"
                    data-testid="run-export-json"
                    onClick={() => {
                      triggerBrowserDownload(
                        runTraceExportFilename(runDetail.run_id),
                        serializeRunTraceJson(runDetail),
                        'application/json',
                      )
                    }}
                  >
                    Export JSON
                  </button>
                </div>
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
              </section>

              <PhaseTimeline runDetail={runDetail} />

              <RunDiagnosisSummary runDetail={runDetail} />

              {runDetail.run_id === detailRunId ? (
                <RunQueuePanel
                  key={runDetail.run_id}
                  runId={runDetail.run_id}
                  runStatus={runDetail.status}
                />
              ) : null}

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

              <div className="cl-diagnosis-stack">
                <RetrievalDiagnosisPanel runDetail={runDetail} />
                <ContextQualityPanel runDetail={runDetail} />
              </div>

              <RetrievalHitsSection
                hits={runDetail.retrieval_hits}
                documentTitleById={documentTitleById}
              />

              <GenerationJudgeInsightsPanel runDetail={runDetail} />

              <RunDiffPanel baseRun={runDetail} />

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
                onClick={() => void loadRegistry({ preserveSelection: true })}
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

      {view === 'dashboard' && (
        <DashboardPanel
          pipelineConfigIds={dashboardCompareIds}
          onOpenRunDetail={(id) => {
            clearMessages()
            setRegistryNotice(null)
            navigate(`/runs/${id}`)
          }}
        />
      )}

      {view === 'queue' && (
        <QueueBrowserPanel pipelineConfigs={pipelineConfigs} registryLoading={registryLoading} />
      )}

      {view === 'document' && <DocumentDetailPanel />}
    </div>
  )
}
