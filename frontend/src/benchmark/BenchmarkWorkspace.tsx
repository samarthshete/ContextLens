import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api } from '../api/client'
import type {
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
import { UploadDocumentPanel } from './UploadDocumentPanel'
import { DashboardPanel } from './DashboardPanel'
import { documentTitleLookupMap } from './retrievalSourceFormat'
import { DocumentDetailPanel } from './DocumentDetailPanel'
import { QueueBrowserPanel } from './QueueBrowserPanel'
import { AppShell } from './AppShell'
import { RunDetailView } from './RunDetailView'
import { ComparisonView } from './ComparisonView'
import { RunsListView } from './RunsListView'
import {
  RUNS_LIST_FILTERS_INIT,
  buildListRunsApiParams,
  narrowRunsOnPage,
  type RunsListServerFilters,
} from './runsListQuery'
import './benchmark.css'

export type View = 'run' | 'runs' | 'queue' | 'detail' | 'compare' | 'dashboard' | 'document'

const RUNS_PAGE = 25

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
  const [diagnosisExperimentMode, setDiagnosisExperimentMode] = useState<'off' | 'manual' | 'assisted'>(
    'off',
  )

  const [compareSelected, setCompareSelected] = useState<Set<number>>(new Set())
  const [compareEvaluator, setCompareEvaluator] = useState<'heuristic' | 'llm' | 'both'>('both')
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

  useEffect(() => {
    setDiagnosisExperimentMode('off')
  }, [detailRunId])

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
    <AppShell view={view} onNavigate={goView}>

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
        <RunsListView
          runs={runs}
          runsVisible={runsVisible}
          runsTotal={runsTotal}
          runsHasMore={runsHasMore}
          runsLoading={runsLoading}
          runsFilters={runsFilters}
          runsNarrowText={runsNarrowText}
          datasets={datasets}
          pipelineConfigs={pipelineConfigs}
          onFiltersChange={(partial) => setRunsFilters((prev) => ({ ...prev, ...partial }))}
          onNarrowTextChange={setRunsNarrowText}
          onClearFilters={clearRunsFilters}
          onRefresh={() => {
            clearMessages()
            void refreshRuns()
          }}
          onLoadMore={() => void loadMoreRuns()}
          onOpenRun={(runId) => {
            clearMessages()
            navigate(`/runs/${runId}`)
          }}
        />
      )}

      {view === 'detail' && (
        <RunDetailView
          routeRunId={params.runId}
          detailRunId={detailRunId}
          runDetail={runDetail}
          detailLoading={detailLoading}
          diagnosisExperimentMode={diagnosisExperimentMode}
          documentTitleById={documentTitleById}
          onDiagnosisModeChange={setDiagnosisExperimentMode}
          onRunIdInputChange={(raw) => {
            const t = raw.trim()
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
      )}

      {view === 'compare' && (
        <ComparisonView
          pipelineConfigs={pipelineConfigs}
          registryLoading={registryLoading}
          compareEvaluator={compareEvaluator}
          compareSelected={compareSelected}
          compareLoading={compareLoading}
          compareResult={compareResult}
          onEvaluatorChange={setCompareEvaluator}
          onToggleCompare={toggleCompare}
          onCompare={() => void handleCompare()}
          onReloadRegistry={() => void loadRegistry({ preserveSelection: true })}
        />
      )}

      {view === 'dashboard' && (
        <DashboardPanel
          pipelineConfigIds={dashboardCompareIds}
          datasets={datasets}
          registryLoading={registryLoading}
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
    </AppShell>
  )
}
