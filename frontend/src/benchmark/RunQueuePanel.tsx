import { useCallback, useEffect, useState } from 'react'
import { api } from '../api/client'
import type { RunQueueStatusResponse } from '../api/types'
import { describeApiError } from './errorMessage'
import { operatorBadgeModifier, presentationFromQueueStatus } from './queueOperatorState'
import { formatQueueField, shouldShowRequeueButton } from './runQueueUi'

type RequeueFeedback = { kind: 'ok' | 'err'; text: string }

/** `runStatus` is the run row lifecycle (`GET /runs/{id}`); when it changes (e.g. polling moves a full run to `completed`), we refetch queue-status so eligibility matches the backend. */
export function RunQueuePanel({ runId, runStatus }: { runId: number; runStatus: string }) {
  const [queueStatus, setQueueStatus] = useState<RunQueueStatusResponse | null>(null)
  const [queueLoading, setQueueLoading] = useState(false)
  const [queueError, setQueueError] = useState<string | null>(null)
  const [requeueBusy, setRequeueBusy] = useState(false)
  const [requeueFeedback, setRequeueFeedback] = useState<RequeueFeedback | null>(null)

  // runStatus in deps (and referenced below) so fetchStatus identity updates when detail poll
  // advances lifecycle; useEffect keeps a fixed-length list [fetchStatus] only.
  const fetchStatus = useCallback(async () => {
    void runStatus
    setQueueLoading(true)
    setQueueError(null)
    try {
      const s = await api.getRunQueueStatus(runId)
      setQueueStatus(s)
    } catch (e) {
      setQueueError(describeApiError(e))
      setQueueStatus(null)
    } finally {
      setQueueLoading(false)
    }
  }, [runId, runStatus])

  useEffect(() => {
    setRequeueFeedback(null)
    setQueueStatus(null)
    void fetchStatus()
  }, [fetchStatus])

  async function handleRequeue() {
    if (!queueStatus || !shouldShowRequeueButton(queueStatus)) return
    setRequeueBusy(true)
    setRequeueFeedback(null)
    try {
      const r = await api.requeueRun(runId)
      setRequeueFeedback({
        kind: 'ok',
        text: `Requeued. New job id: ${r.job_id}. Refresh queue status below to confirm lock/RQ fields.`,
      })
      await fetchStatus()
    } catch (e) {
      setRequeueFeedback({ kind: 'err', text: describeApiError(e) })
    } finally {
      setRequeueBusy(false)
    }
  }

  const refreshDisabled = queueLoading || requeueBusy
  const showRequeue = queueStatus != null && shouldShowRequeueButton(queueStatus)
  const operatorReadout =
    queueStatus && !queueError ? presentationFromQueueStatus(queueStatus) : null

  return (
    <section className="cl-subsection cl-queue-panel" aria-labelledby="cl-queue-heading">
      <div className="cl-queue-header">
        <h3 id="cl-queue-heading">Queue &amp; requeue</h3>
        <button
          type="button"
          className="cl-btn cl-btn-secondary cl-btn-sm"
          onClick={() => void fetchStatus()}
          disabled={refreshDisabled}
        >
          {queueLoading ? 'Refreshing…' : 'Refresh queue status'}
        </button>
      </div>

      {queueError ? (
        <p className="cl-msg cl-msg-error" role="alert">
          {queueError}
        </p>
      ) : null}

      {requeueFeedback ? (
        <p
          className={`cl-msg ${requeueFeedback.kind === 'ok' ? 'cl-msg-ok' : 'cl-msg-error'}`}
          role="status"
        >
          {requeueFeedback.text}
        </p>
      ) : null}

      {!queueStatus && !queueError && queueLoading ? (
        <p className="cl-muted">Loading queue status…</p>
      ) : null}

      {operatorReadout ? (
        <div className="cl-queue-operator-readout" data-testid="run-queue-operator-readout">
          <span
            className={`cl-queue-op-badge cl-queue-op--${operatorBadgeModifier(operatorReadout)}`}
            title={operatorReadout.description}
          >
            {operatorReadout.badge}
          </span>
          <p className="cl-muted cl-queue-op-desc">{operatorReadout.description}</p>
        </div>
      ) : null}

      {queueStatus?.pipeline === 'full' ? (
        <>
          <dl className="cl-queue-dl">
            <div className="cl-queue-row">
              <dt>Pipeline</dt>
              <dd>{queueStatus.pipeline}</dd>
            </div>
            <div className="cl-queue-row">
              <dt>Job id</dt>
              <dd>
                <code>{formatQueueField(queueStatus.job_id ?? undefined)}</code>
              </dd>
            </div>
            <div className="cl-queue-row">
              <dt>RQ job status</dt>
              <dd>{formatQueueField(queueStatus.rq_job_status ?? undefined)}</dd>
            </div>
            <div className="cl-queue-row">
              <dt>Lock present</dt>
              <dd>{queueStatus.lock_present ? 'yes' : 'no'}</dd>
            </div>
            <div className="cl-queue-row">
              <dt>Requeue eligible</dt>
              <dd>{queueStatus.requeue_eligible ? 'yes' : 'no'}</dd>
            </div>
            <div className="cl-queue-row">
              <dt>Detail</dt>
              <dd>{formatQueueField(queueStatus.detail ?? undefined)}</dd>
            </div>
          </dl>
          {showRequeue ? (
            <div className="cl-queue-actions">
              <button
                type="button"
                className="cl-btn"
                onClick={() => void handleRequeue()}
                disabled={requeueBusy || queueLoading}
              >
                {requeueBusy ? 'Requeuing…' : 'Requeue full run'}
              </button>
            </div>
          ) : null}
        </>
      ) : null}
    </section>
  )
}
