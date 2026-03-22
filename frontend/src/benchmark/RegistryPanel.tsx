import { useCallback, useEffect, useState } from 'react'
import { api, ApiError } from '../api/client'
import type { Dataset, PipelineConfig, QueryCase } from '../api/types'
import { describeApiError } from './errorMessage'
import { validatePipelineChunkParams, validateTopK } from './registryFormValidation'

export type RegistryNotice = { kind: 'ok' | 'err'; text: string }

type Props = {
  datasets: Dataset[]
  pipelineConfigs: PipelineConfig[]
  selectedDatasetId: number | ''
  registryLoading: boolean
  onPreservingReload: () => Promise<void>
  notice: RegistryNotice | null
  setNotice: (n: RegistryNotice | null) => void
  onCreatedDataset: (id: number) => void
  onCreatedQueryCase: (id: number) => void
  onCreatedPipelineConfig: (id: number) => void
}

const DEFAULT_EMBEDDING = 'all-MiniLM-L6-v2'

export function RegistryPanel({
  datasets,
  pipelineConfigs,
  selectedDatasetId,
  registryLoading,
  onPreservingReload,
  notice,
  setNotice,
  onCreatedDataset,
  onCreatedQueryCase,
  onCreatedPipelineConfig,
}: Props) {
  const [busy, setBusy] = useState(false)

  const [newDsName, setNewDsName] = useState('')
  const [newDsDesc, setNewDsDesc] = useState('')
  const [editDsId, setEditDsId] = useState<number | null>(null)
  const [editDsName, setEditDsName] = useState('')
  const [editDsDesc, setEditDsDesc] = useState('')

  const [qcDatasetId, setQcDatasetId] = useState<number | ''>('')
  const [qcList, setQcList] = useState<QueryCase[]>([])
  const [qcListLoading, setQcListLoading] = useState(false)
  const [newQcText, setNewQcText] = useState('')
  const [newQcExpected, setNewQcExpected] = useState('')
  const [editQcId, setEditQcId] = useState<number | null>(null)
  const [editQcText, setEditQcText] = useState('')
  const [editQcExpected, setEditQcExpected] = useState('')

  const [newPcName, setNewPcName] = useState('')
  const [newPcStrategy, setNewPcStrategy] = useState<'fixed' | 'recursive'>('fixed')
  const [newPcSize, setNewPcSize] = useState(512)
  const [newPcOverlap, setNewPcOverlap] = useState(0)
  const [newPcTopK, setNewPcTopK] = useState(5)
  const [editPcId, setEditPcId] = useState<number | null>(null)
  const [editPcName, setEditPcName] = useState('')
  const [editPcStrategy, setEditPcStrategy] = useState('fixed')
  const [editPcSize, setEditPcSize] = useState(512)
  const [editPcOverlap, setEditPcOverlap] = useState(0)
  const [editPcTopK, setEditPcTopK] = useState(5)

  const runMutation = useCallback(
    async (fn: () => Promise<void>) => {
      setNotice(null)
      setBusy(true)
      try {
        await fn()
      } catch (e) {
        setNotice({ kind: 'err', text: describeApiError(e) })
      } finally {
        setBusy(false)
      }
    },
    [setNotice],
  )

  useEffect(() => {
    if (selectedDatasetId !== '') {
      setQcDatasetId((prev) => (prev === '' ? selectedDatasetId : prev))
    }
  }, [selectedDatasetId])

  useEffect(() => {
    if (qcDatasetId !== '' && !datasets.some((d) => d.id === qcDatasetId)) {
      setQcDatasetId(datasets[0]?.id ?? '')
    }
  }, [datasets, qcDatasetId])

  const refetchQueryCases = useCallback(async () => {
    if (qcDatasetId === '') {
      setQcList([])
      return
    }
    setQcListLoading(true)
    try {
      const qc = await api.listQueryCases(Number(qcDatasetId))
      setQcList(qc)
    } catch (e) {
      setQcList([])
      setNotice({ kind: 'err', text: describeApiError(e) })
    } finally {
      setQcListLoading(false)
    }
  }, [qcDatasetId, setNotice])

  useEffect(() => {
    void refetchQueryCases()
  }, [refetchQueryCases])

  const startEditDs = (d: Dataset) => {
    setEditDsId(d.id)
    setEditDsName(d.name)
    setEditDsDesc(d.description ?? '')
  }

  const cancelEditDs = () => {
    setEditDsId(null)
  }

  const startEditQc = (q: QueryCase) => {
    setEditQcId(q.id)
    setEditQcText(q.query_text)
    setEditQcExpected(q.expected_answer ?? '')
  }

  const startEditPc = (p: PipelineConfig) => {
    setEditPcId(p.id)
    setEditPcName(p.name)
    setEditPcStrategy(p.chunk_strategy === 'recursive' ? 'recursive' : 'fixed')
    setEditPcSize(p.chunk_size)
    setEditPcOverlap(p.chunk_overlap)
    setEditPcTopK(p.top_k)
  }

  const disabled = busy || registryLoading

  return (
    <section className="cl-card cl-registry-panel" aria-labelledby="registry-heading">
      <h2 id="registry-heading">Benchmark registry</h2>
      <p className="cl-muted cl-registry-lead">
        Create or edit datasets, query cases, and pipeline configs (same APIs as{' '}
        <code>POST/PATCH/DELETE /api/v1/…</code>). Selections in <strong>Start a run</strong> below update when you
        save here.
      </p>

      {notice ? (
        <div
          className={notice.kind === 'ok' ? 'cl-msg cl-msg-ok cl-registry-msg' : 'cl-msg cl-msg-error cl-registry-msg'}
          role={notice.kind === 'ok' ? 'status' : 'alert'}
        >
          {notice.text}
        </div>
      ) : null}

      <fieldset className="cl-registry-fieldset" disabled={disabled}>
        <legend className="cl-registry-legend">Datasets</legend>
        <div className="cl-registry-grid">
          <div className="cl-registry-form">
            <h3 className="cl-h4">New dataset</h3>
            <div className="cl-field">
              <label htmlFor="new-ds-name">Name</label>
              <input
                id="new-ds-name"
                type="text"
                value={newDsName}
                onChange={(e) => setNewDsName(e.target.value)}
                placeholder="e.g. Legal smoke tests"
                autoComplete="off"
              />
            </div>
            <div className="cl-field">
              <label htmlFor="new-ds-desc">Description (optional)</label>
              <input
                id="new-ds-desc"
                type="text"
                value={newDsDesc}
                onChange={(e) => setNewDsDesc(e.target.value)}
                autoComplete="off"
              />
            </div>
            <button
              type="button"
              className="cl-btn cl-btn-secondary"
              disabled={!newDsName.trim()}
              onClick={() =>
                void runMutation(async () => {
                  const created = await api.createDataset({
                    name: newDsName.trim(),
                    description: newDsDesc.trim() || null,
                  })
                  setNewDsName('')
                  setNewDsDesc('')
                  await onPreservingReload()
                  onCreatedDataset(created.id)
                  setNotice({ kind: 'ok', text: `Dataset “${created.name}” created (id ${created.id}).` })
                })
              }
            >
              Create dataset
            </button>
          </div>

          <div className="cl-registry-list-wrap">
            <h3 className="cl-h4">Existing</h3>
            {!datasets.length ? (
              <p className="cl-muted">No datasets yet.</p>
            ) : (
              <ul className="cl-registry-list">
                {datasets.map((d) => (
                  <li key={d.id} className="cl-registry-row">
                    {editDsId === d.id ? (
                      <div className="cl-registry-edit">
                        <input
                          type="text"
                          value={editDsName}
                          onChange={(e) => setEditDsName(e.target.value)}
                          aria-label="Dataset name"
                        />
                        <input
                          type="text"
                          value={editDsDesc}
                          onChange={(e) => setEditDsDesc(e.target.value)}
                          placeholder="Description"
                          aria-label="Dataset description"
                        />
                        <div className="cl-actions cl-actions-tight">
                          <button
                            type="button"
                            className="cl-btn"
                            disabled={!editDsName.trim()}
                            onClick={() =>
                              void runMutation(async () => {
                                await api.updateDataset(d.id, {
                                  name: editDsName.trim(),
                                  description: editDsDesc.trim() || null,
                                })
                                cancelEditDs()
                                await onPreservingReload()
                                setNotice({ kind: 'ok', text: `Dataset #${d.id} updated.` })
                              })
                            }
                          >
                            Save
                          </button>
                          <button type="button" className="cl-btn cl-btn-secondary" onClick={cancelEditDs}>
                            Cancel
                          </button>
                        </div>
                      </div>
                    ) : (
                      <>
                        <div className="cl-registry-row-main">
                          <strong>{d.name}</strong>
                          <span className="cl-muted">id {d.id}</span>
                          {d.description ? <span className="cl-registry-desc">{d.description}</span> : null}
                        </div>
                        <div className="cl-registry-row-actions">
                          <button type="button" className="link" onClick={() => startEditDs(d)}>
                            Edit
                          </button>
                          <button
                            type="button"
                            className="link cl-link-danger"
                            onClick={() => {
                              if (
                                !window.confirm(
                                  `Delete dataset “${d.name}” (id ${d.id})? Blocked if query cases exist (409).`,
                                )
                              ) {
                                return
                              }
                              void runMutation(async () => {
                                try {
                                  await api.deleteDataset(d.id)
                                } catch (e) {
                                  if (e instanceof ApiError && e.status === 409) {
                                    setNotice({
                                      kind: 'err',
                                      text: e.detail || 'Cannot delete: query cases still reference this dataset.',
                                    })
                                    return
                                  }
                                  throw e
                                }
                                await onPreservingReload()
                                setNotice({ kind: 'ok', text: `Dataset #${d.id} deleted.` })
                              })
                            }}
                          >
                            Delete
                          </button>
                        </div>
                      </>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </fieldset>

      <fieldset className="cl-registry-fieldset" disabled={disabled}>
        <legend className="cl-registry-legend">Query cases</legend>
        <div className="cl-field">
          <label htmlFor="qc-manage-dataset">Dataset for query cases</label>
          <select
            id="qc-manage-dataset"
            value={qcDatasetId === '' ? '' : String(qcDatasetId)}
            onChange={(e) => setQcDatasetId(e.target.value === '' ? '' : Number(e.target.value))}
          >
            <option value="">Select dataset…</option>
            {datasets.map((d) => (
              <option key={d.id} value={d.id}>
                {d.name} (id {d.id})
              </option>
            ))}
          </select>
          <p className="cl-field-hint">Choose which dataset’s queries you are editing (defaults to the run form dataset when set).</p>
        </div>

        {qcDatasetId === '' ? (
          <p className="cl-muted">Select a dataset to list or add query cases.</p>
        ) : qcListLoading ? (
          <p className="cl-loading-inline">Loading query cases…</p>
        ) : (
          <>
            <div className="cl-registry-form">
              <h3 className="cl-h4">New query case</h3>
              <div className="cl-field">
                <label htmlFor="new-qc-text">Query text</label>
                <textarea
                  id="new-qc-text"
                  rows={2}
                  value={newQcText}
                  onChange={(e) => setNewQcText(e.target.value)}
                  placeholder="Question to run against the corpus"
                />
              </div>
              <div className="cl-field">
                <label htmlFor="new-qc-exp">Expected answer (optional)</label>
                <input
                  id="new-qc-exp"
                  type="text"
                  value={newQcExpected}
                  onChange={(e) => setNewQcExpected(e.target.value)}
                />
              </div>
              <button
                type="button"
                className="cl-btn cl-btn-secondary"
                disabled={!newQcText.trim()}
                onClick={() =>
                  void runMutation(async () => {
                    const created = await api.createQueryCase({
                      dataset_id: Number(qcDatasetId),
                      query_text: newQcText.trim(),
                      expected_answer: newQcExpected.trim() || null,
                    })
                    setNewQcText('')
                    setNewQcExpected('')
                    await refetchQueryCases()
                    await onPreservingReload()
                    onCreatedQueryCase(created.id)
                    setNotice({ kind: 'ok', text: `Query case #${created.id} created.` })
                  })
                }
              >
                Add query case
              </button>
            </div>

            <h3 className="cl-h4">In this dataset</h3>
            {!qcList.length ? (
              <p className="cl-muted">No query cases yet.</p>
            ) : (
              <ul className="cl-registry-list">
                {qcList.map((q) => (
                  <li key={q.id} className="cl-registry-row">
                    {editQcId === q.id ? (
                      <div className="cl-registry-edit">
                        <textarea
                          rows={2}
                          value={editQcText}
                          onChange={(e) => setEditQcText(e.target.value)}
                          aria-label="Query text"
                        />
                        <input
                          type="text"
                          value={editQcExpected}
                          onChange={(e) => setEditQcExpected(e.target.value)}
                          placeholder="Expected answer (optional)"
                        />
                        <div className="cl-actions cl-actions-tight">
                          <button
                            type="button"
                            className="cl-btn"
                            disabled={!editQcText.trim()}
                            onClick={() =>
                              void runMutation(async () => {
                                await api.updateQueryCase(q.id, {
                                  query_text: editQcText.trim(),
                                  expected_answer: editQcExpected.trim() || null,
                                })
                                setEditQcId(null)
                                await refetchQueryCases()
                                await onPreservingReload()
                                setNotice({ kind: 'ok', text: `Query case #${q.id} updated.` })
                              })
                            }
                          >
                            Save
                          </button>
                          <button type="button" className="cl-btn cl-btn-secondary" onClick={() => setEditQcId(null)}>
                            Cancel
                          </button>
                        </div>
                      </div>
                    ) : (
                      <>
                        <div className="cl-registry-row-main">
                          <span className="cl-registry-qtext">{q.query_text}</span>
                          <span className="cl-muted">id {q.id}</span>
                        </div>
                        <div className="cl-registry-row-actions">
                          <button type="button" className="link" onClick={() => startEditQc(q)}>
                            Edit
                          </button>
                          <button
                            type="button"
                            className="link cl-link-danger"
                            onClick={() => {
                              if (!window.confirm(`Delete query case #${q.id}? Blocked if runs exist (409).`)) return
                              void runMutation(async () => {
                                try {
                                  await api.deleteQueryCase(q.id)
                                } catch (e) {
                                  if (e instanceof ApiError && e.status === 409) {
                                    setNotice({
                                      kind: 'err',
                                      text: e.detail || 'Cannot delete: runs still reference this query case.',
                                    })
                                    return
                                  }
                                  throw e
                                }
                                await refetchQueryCases()
                                await onPreservingReload()
                                setNotice({ kind: 'ok', text: `Query case #${q.id} deleted.` })
                              })
                            }}
                          >
                            Delete
                          </button>
                        </div>
                      </>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </>
        )}
      </fieldset>

      <fieldset className="cl-registry-fieldset" disabled={disabled}>
        <legend className="cl-registry-legend">Pipeline configs</legend>
        <div className="cl-registry-grid">
          <div className="cl-registry-form">
            <h3 className="cl-h4">New pipeline config</h3>
            <div className="cl-field">
              <label htmlFor="new-pc-name">Name</label>
              <input
                id="new-pc-name"
                type="text"
                value={newPcName}
                onChange={(e) => setNewPcName(e.target.value)}
                placeholder="e.g. baseline-256"
              />
            </div>
            <div className="cl-field">
              <label htmlFor="new-pc-strat">Chunk strategy</label>
              <select
                id="new-pc-strat"
                value={newPcStrategy}
                onChange={(e) => setNewPcStrategy(e.target.value as 'fixed' | 'recursive')}
              >
                <option value="fixed">fixed</option>
                <option value="recursive">recursive</option>
              </select>
            </div>
            <div className="cl-field-row">
              <div className="cl-field">
                <label htmlFor="new-pc-size">Chunk size</label>
                <input
                  id="new-pc-size"
                  type="number"
                  min={1}
                  value={newPcSize}
                  onChange={(e) => setNewPcSize(Number(e.target.value))}
                />
              </div>
              <div className="cl-field">
                <label htmlFor="new-pc-overlap">Overlap</label>
                <input
                  id="new-pc-overlap"
                  type="number"
                  min={0}
                  value={newPcOverlap}
                  onChange={(e) => setNewPcOverlap(Number(e.target.value))}
                />
              </div>
              <div className="cl-field">
                <label htmlFor="new-pc-topk">top_k</label>
                <input
                  id="new-pc-topk"
                  type="number"
                  min={1}
                  value={newPcTopK}
                  onChange={(e) => setNewPcTopK(Number(e.target.value))}
                />
              </div>
            </div>
            <button
              type="button"
              className="cl-btn cl-btn-secondary"
              disabled={!newPcName.trim()}
              onClick={() => {
                const v = validatePipelineChunkParams(newPcSize, newPcOverlap)
                if (!v.ok) {
                  setNotice({ kind: 'err', text: v.message })
                  return
                }
                const tk = validateTopK(newPcTopK)
                if (!tk.ok) {
                  setNotice({ kind: 'err', text: tk.message })
                  return
                }
                void runMutation(async () => {
                  const created = await api.createPipelineConfig({
                    name: newPcName.trim(),
                    embedding_model: DEFAULT_EMBEDDING,
                    chunk_strategy: newPcStrategy,
                    chunk_size: newPcSize,
                    chunk_overlap: newPcOverlap,
                    top_k: newPcTopK,
                  })
                  setNewPcName('')
                  await onPreservingReload()
                  onCreatedPipelineConfig(created.id)
                  setNotice({ kind: 'ok', text: `Pipeline config “${created.name}” created (id ${created.id}).` })
                })
              }}
            >
              Create pipeline config
            </button>
          </div>

          <div className="cl-registry-list-wrap">
            <h3 className="cl-h4">Existing</h3>
            {!pipelineConfigs.length ? (
              <p className="cl-muted">No pipeline configs yet.</p>
            ) : (
              <ul className="cl-registry-list">
                {pipelineConfigs.map((p) => (
                  <li key={p.id} className="cl-registry-row">
                    {editPcId === p.id ? (
                      <div className="cl-registry-edit">
                        <input
                          type="text"
                          value={editPcName}
                          onChange={(e) => setEditPcName(e.target.value)}
                          aria-label="Config name"
                        />
                        <select
                          value={editPcStrategy}
                          onChange={(e) => setEditPcStrategy(e.target.value)}
                          aria-label="Chunk strategy"
                        >
                          <option value="fixed">fixed</option>
                          <option value="recursive">recursive</option>
                        </select>
                        <div className="cl-field-row">
                          <input
                            type="number"
                            min={1}
                            value={editPcSize}
                            onChange={(e) => setEditPcSize(Number(e.target.value))}
                            aria-label="Chunk size"
                          />
                          <input
                            type="number"
                            min={0}
                            value={editPcOverlap}
                            onChange={(e) => setEditPcOverlap(Number(e.target.value))}
                            aria-label="Overlap"
                          />
                          <input
                            type="number"
                            min={1}
                            value={editPcTopK}
                            onChange={(e) => setEditPcTopK(Number(e.target.value))}
                            aria-label="top_k"
                          />
                        </div>
                        <div className="cl-actions cl-actions-tight">
                          <button
                            type="button"
                            className="cl-btn"
                            disabled={!editPcName.trim()}
                            onClick={() => {
                              const v = validatePipelineChunkParams(editPcSize, editPcOverlap)
                              if (!v.ok) {
                                setNotice({ kind: 'err', text: v.message })
                                return
                              }
                              const tk = validateTopK(editPcTopK)
                              if (!tk.ok) {
                                setNotice({ kind: 'err', text: tk.message })
                                return
                              }
                              void runMutation(async () => {
                                await api.updatePipelineConfig(p.id, {
                                  name: editPcName.trim(),
                                  chunk_strategy: editPcStrategy,
                                  chunk_size: editPcSize,
                                  chunk_overlap: editPcOverlap,
                                  top_k: editPcTopK,
                                })
                                setEditPcId(null)
                                await onPreservingReload()
                                setNotice({ kind: 'ok', text: `Pipeline config #${p.id} updated.` })
                              })
                            }}
                          >
                            Save
                          </button>
                          <button type="button" className="cl-btn cl-btn-secondary" onClick={() => setEditPcId(null)}>
                            Cancel
                          </button>
                        </div>
                      </div>
                    ) : (
                      <>
                        <div className="cl-registry-row-main">
                          <strong>{p.name}</strong>
                          <span className="cl-muted">
                            id {p.id} · {p.chunk_strategy} · size {p.chunk_size} · overlap {p.chunk_overlap} · top_k{' '}
                            {p.top_k}
                          </span>
                        </div>
                        <div className="cl-registry-row-actions">
                          <button type="button" className="link" onClick={() => startEditPc(p)}>
                            Edit
                          </button>
                          <button
                            type="button"
                            className="link cl-link-danger"
                            onClick={() => {
                              if (!window.confirm(`Delete pipeline config “${p.name}” (id ${p.id})? Blocked if runs exist (409).`))
                                return
                              void runMutation(async () => {
                                try {
                                  await api.deletePipelineConfig(p.id)
                                } catch (e) {
                                  if (e instanceof ApiError && e.status === 409) {
                                    setNotice({
                                      kind: 'err',
                                      text: e.detail || 'Cannot delete: runs still reference this config.',
                                    })
                                    return
                                  }
                                  throw e
                                }
                                await onPreservingReload()
                                setNotice({ kind: 'ok', text: `Pipeline config #${p.id} deleted.` })
                              })
                            }}
                          >
                            Delete
                          </button>
                        </div>
                      </>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </fieldset>
    </section>
  )
}
