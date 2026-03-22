import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import type { PipelineConfig, RunListItem, RunQueueStatusResponse } from '../api/types'
import { describeApiError } from './errorMessage'
import { QUEUE_BROWSER_STATUS_SLICES, loadQueueBrowserRunRows } from './queueBrowserLoad'
import {
  operatorBadgeModifier,
  parseQueueRowRemoteState,
  presentationFromRowState,
} from './queueOperatorState'
import { formatQueueField, shouldShowRequeueButton } from './runQueueUi'

function formatWhen(iso: string): string {
  try {
    return new Date(iso).toLocaleString()
  } catch {
    return iso
  }
}

function pipelineLabel(id: number, configs: PipelineConfig[]): string {
  const p = configs.find((c) => c.id === id)
  return p ? `${p.name} (#${id})` : `config #${id}`
}

type RowQueueState = {
  loading: boolean
  data: RunQueueStatusResponse | null
  error: string | null
}

export function QueueBrowserPanel({
  pipelineConfigs,
  registryLoading,
}: {
  pipelineConfigs: PipelineConfig[]
  registryLoading: boolean
}) {
  const navigate = useNavigate()
  const [rows, setRows] = useState<RunListItem[]>([])
  const [listLoading, setListLoading] = useState(false)
  const [listError, setListError] = useState<string | null>(null)
  const [sliceErrors, setSliceErrors] = useState<string[]>([])
  const [qsByRunId, setQsByRunId] = useState<Record<number, RowQueueState>>({})
  const [requeueBusyId, setRequeueBusyId] = useState<number | null>(null)
  const [requeueNotice, setRequeueNotice] = useState<{
    runId: number
    kind: 'ok' | 'err'
    text: string
  } | null>(null)

  const loadList = useCallback(async (clearRequeueNotice = true) => {
    if (clearRequeueNotice) {
      setRequeueNotice(null)
    }
    setListLoading(true)
    setListError(null)
    setSliceErrors([])
    try {
      const { items, sliceErrors: se } = await loadQueueBrowserRunRows((p) => api.listRuns(p))
      setRows(items)
      setSliceErrors(se)
      if (se.length === QUEUE_BROWSER_STATUS_SLICES.length && items.length === 0) {
        setListError('Could not load any run slices. Check API connectivity.')
      }
    } catch (e) {
      setListError(describeApiError(e))
      setRows([])
    } finally {
      setListLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadList()
  }, [loadList])

  const refreshQueueRow = useCallback(async (runId: number) => {
    setQsByRunId((prev) => ({
      ...prev,
      [runId]: {
        loading: true,
        data: prev[runId]?.data ?? null,
        error: null,
      },
    }))
    try {
      const s = await api.getRunQueueStatus(runId)
      setQsByRunId((prev) => ({
        ...prev,
        [runId]: { loading: false, data: s, error: null },
      }))
    } catch (e) {
      setQsByRunId((prev) => ({
        ...prev,
        [runId]: { loading: false, data: null, error: describeApiError(e) },
      }))
    }
  }, [])

  const handleRequeue = useCallback(
    async (runId: number) => {
      setRequeueNotice(null)
      setRequeueBusyId(runId)
      try {
        const r = await api.requeueRun(runId)
        await refreshQueueRow(runId)
        await loadList(false)
        setRequeueNotice({
          runId,
          kind: 'ok',
          text: `Run ${runId} requeued (job ${r.job_id}). Queue status row refreshed; list reloaded so run status stays honest.`,
        })
      } catch (e) {
        const msg = describeApiError(e)
        setRequeueNotice({ runId, kind: 'err', text: msg })
        setQsByRunId((prev) => ({
          ...prev,
          [runId]: {
            loading: false,
            data: prev[runId]?.data ?? null,
            error: msg,
          },
        }))
      } finally {
        setRequeueBusyId(null)
      }
    },
    [refreshQueueRow, loadList],
  )

  return (
    <section className="cl-card" data-testid="queue-browser">
      <h2>Queue browser</h2>
      <p className="cl-muted">
        Operator view for <strong>non-terminal</strong> and <strong>failed</strong> runs. Rows come from parallel{' '}
        <code>GET /runs</code> slices (pending, running, mid-pipeline, failed), merged and capped.{' '}
        <strong>Queue status</strong> is loaded only when you click refresh on a row — same endpoint as run detail’s{' '}
        <em>Queue &amp; requeue</em> panel.
      </p>
      <p className="cl-muted">
        Evaluator column is from the list API (<code>heuristic</code> / <code>llm</code> / <code>none</code>) — not a
        guarantee of full vs heuristic <em>submission</em> mode. Use queue status after refresh for Redis/RQ truth.
      </p>
      <p className="cl-muted cl-queue-browser-recovery-hint">
        <strong>Interrupted / failed full runs:</strong> click <strong>Queue status</strong>. When the operator badge reads{' '}
        <em>Recovery: can requeue</em>, use <strong>Requeue</strong> — the list reloads automatically so the{' '}
        <strong>Status</strong> column catches up. <em>Blocked: worker lock</em> means POST /requeue would 409 until the lock
        clears (queue-status may clear stale locks when RQ shows a terminal failed job — retry refresh). <em>Heuristic (no queue)</em>{' '}
        means no RQ path for that run.
      </p>

      <div className="cl-actions">
        <button
          type="button"
          className="cl-btn cl-btn-secondary"
          data-testid="queue-browser-refresh-list"
          disabled={listLoading}
          onClick={() => void loadList()}
        >
          {listLoading ? 'Loading…' : 'Refresh list'}
        </button>
      </div>

      {registryLoading ? (
        <p className="cl-muted">Pipeline names load with the registry…</p>
      ) : null}

      {listError ? (
        <p className="cl-msg cl-msg-error" role="alert">
          {listError}
        </p>
      ) : null}

      {sliceErrors.length > 0 && !listError ? (
        <p className="cl-msg cl-msg-error" role="status">
          Some status slices failed: {sliceErrors.join(' · ')}
        </p>
      ) : null}

      {requeueNotice ? (
        <p
          className={`cl-msg ${requeueNotice.kind === 'ok' ? 'cl-msg-ok' : 'cl-msg-error'}`}
          role="status"
          data-testid="queue-browser-requeue-notice"
        >
          {requeueNotice.text}
        </p>
      ) : null}

      {listLoading && rows.length === 0 ? <p className="cl-loading">Loading runs…</p> : null}

      {!listLoading && rows.length === 0 && !listError ? (
        <p className="cl-empty-banner" data-testid="queue-browser-empty">
          No runs in pending, running, mid-pipeline, or failed states (within loaded slices). Check{' '}
          <strong>Recent runs</strong> for completed history.
        </p>
      ) : null}

      {rows.length > 0 ? (
        <div className="cl-table-wrap cl-queue-browser-table-wrap">
          <table className="cl-table" data-testid="queue-browser-table">
            <thead>
              <tr>
                <th>Run</th>
                <th>Status</th>
                <th>Evaluator</th>
                <th>Pipeline</th>
                <th>Created</th>
                <th>Operator readout</th>
                <th>Queue pipeline</th>
                <th>Job id</th>
                <th>RQ status</th>
                <th>Lock</th>
                <th>Requeue OK</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => {
                const qs = qsByRunId[r.run_id]
                const d = qs?.data
                const loading = qs?.loading === true
                const err = qs?.error
                const remote = parseQueueRowRemoteState(qs)
                const pres = presentationFromRowState(remote)
                const showRequeue =
                  d != null && shouldShowRequeueButton(d) && requeueBusyId !== r.run_id && !loading
                return (
                  <tr key={r.run_id} data-testid={`queue-browser-row-${r.run_id}`}>
                    <td>{r.run_id}</td>
                    <td>{r.status.replace(/_/g, ' ')}</td>
                    <td>{r.evaluator_type}</td>
                    <td className="cl-td-wrap">{pipelineLabel(r.pipeline_config_id, pipelineConfigs)}</td>
                    <td>{formatWhen(r.created_at)}</td>
                    <td className="cl-td-wrap cl-queue-browser-op-cell">
                      <span
                        className={`cl-queue-op-badge cl-queue-op--${operatorBadgeModifier(pres)}`}
                        title={pres.description}
                        data-testid={`queue-browser-op-badge-${r.run_id}`}
                      >
                        {pres.badge}
                      </span>
                    </td>
                    <td className="cl-td-wrap">
                      {loading ? (
                        <span className="cl-muted">Loading…</span>
                      ) : err ? (
                        <span className="cl-queue-browser-cell-err" title={err}>
                          {err}
                        </span>
                      ) : d?.pipeline === 'heuristic' ? (
                        <span className="cl-muted" data-testid={`queue-browser-heuristic-${r.run_id}`}>
                          heuristic (no RQ)
                        </span>
                      ) : d?.pipeline === 'full' ? (
                        'full'
                      ) : (
                        '—'
                      )}
                    </td>
                    <td>
                      <code className="cl-code-tight">{d?.pipeline === 'full' ? formatQueueField(d.job_id) : '—'}</code>
                    </td>
                    <td>{d?.pipeline === 'full' ? formatQueueField(d.rq_job_status) : '—'}</td>
                    <td>
                      {d?.pipeline === 'full' ? (d.lock_present ? 'yes' : 'no') : '—'}
                    </td>
                    <td>
                      {d?.pipeline === 'full' ? (d.requeue_eligible ? 'yes' : 'no') : '—'}
                    </td>
                    <td>
                      <div className="cl-queue-browser-actions">
                        <button
                          type="button"
                          className="link"
                          onClick={() => {
                            navigate(`/runs/${r.run_id}`)
                          }}
                        >
                          Open
                        </button>
                        <button
                          type="button"
                          className="cl-btn cl-btn-secondary cl-btn-sm"
                          data-testid={`queue-browser-refresh-qs-${r.run_id}`}
                          disabled={loading || requeueBusyId === r.run_id}
                          onClick={() => void refreshQueueRow(r.run_id)}
                        >
                          {loading ? '…' : 'Queue status'}
                        </button>
                        {showRequeue ? (
                          <button
                            type="button"
                            className="cl-btn cl-btn-sm"
                            disabled={requeueBusyId === r.run_id}
                            onClick={() => void handleRequeue(r.run_id)}
                          >
                            {requeueBusyId === r.run_id ? '…' : 'Requeue'}
                          </button>
                        ) : null}
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      ) : null}
    </section>
  )
}
