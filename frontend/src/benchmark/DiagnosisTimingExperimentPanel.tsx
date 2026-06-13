import { useCallback, useEffect, useState } from 'react'
import { api, ApiError } from '../api/client'
import type { DiagnosisTimingSession } from '../api/types'

export type DiagnosisExperimentMode = 'off' | 'manual' | 'assisted'

type Props = {
  runId: number
  onModeChange: (mode: DiagnosisExperimentMode) => void
}

function fmtSec(sec: number | null | undefined): string {
  if (sec == null || Number.isNaN(sec)) return '—'
  return `${sec.toFixed(1)}s`
}

export function DiagnosisTimingExperimentPanel({ runId, onModeChange }: Props) {
  const [experimentMode, setExperimentMode] = useState<DiagnosisExperimentMode>('off')
  const [sessions, setSessions] = useState<DiagnosisTimingSession[]>([])
  const [activeSessionId, setActiveSessionId] = useState<number | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      const rows = await api.listDiagnosisTimingSessions(runId)
      setSessions(rows)
    } catch (e) {
      if (e instanceof ApiError) setError(e.detail)
      else setError('Failed to load diagnosis sessions')
    }
  }, [runId])

  useEffect(() => {
    void load()
  }, [load])

  const setMode = (m: DiagnosisExperimentMode) => {
    setExperimentMode(m)
    onModeChange(m)
  }

  async function startSession(mode: 'manual' | 'assisted') {
    setBusy(true)
    setError(null)
    try {
      const row = await api.createDiagnosisTimingSession(runId, { mode })
      setActiveSessionId(row.id)
      await load()
    } catch (e) {
      if (e instanceof ApiError) setError(e.detail)
      else setError('Could not start session')
    } finally {
      setBusy(false)
    }
  }

  async function patchSession(
    sessionId: number,
    body: Parameters<typeof api.patchDiagnosisTimingSession>[2],
  ) {
    setBusy(true)
    setError(null)
    try {
      await api.patchDiagnosisTimingSession(runId, sessionId, body)
      await load()
    } catch (e) {
      if (e instanceof ApiError) setError(e.detail)
      else setError('Could not update session')
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="cl-subsection cl-card" data-testid="diagnosis-timing-experiment">
      <h3>Diagnosis timing experiment</h3>
      <p className="cl-muted">
        Record <strong>started → first insight → completed</strong> timestamps for manual vs assisted review.
        Dashboard aggregates use persisted sessions only (synthetic test sessions excluded from evidence).
      </p>
      <div className="cl-field">
        <span className="cl-stage-label">Experiment display mode</span>
        <div className="cl-diagnosis-mode-row">
          <label>
            <input
              type="radio"
              name={`diag-mode-${runId}`}
              checked={experimentMode === 'off'}
              onChange={() => setMode('off')}
            />{' '}
            Off (normal UI)
          </label>
          <label>
            <input
              type="radio"
              name={`diag-mode-${runId}`}
              checked={experimentMode === 'manual'}
              onChange={() => setMode('manual')}
            />{' '}
            Manual baseline (hide assisted diagnosis widgets below)
          </label>
          <label>
            <input
              type="radio"
              name={`diag-mode-${runId}`}
              checked={experimentMode === 'assisted'}
              onChange={() => setMode('assisted')}
            />{' '}
            Assisted (full diagnosis UI)
          </label>
        </div>
      </div>
      <div className="cl-btn-row cl-diagnosis-timing-actions">
        <button
          type="button"
          className="cl-btn cl-btn-secondary cl-btn-sm"
          disabled={busy}
          onClick={() => void startSession('manual')}
        >
          Start manual session
        </button>
        <button
          type="button"
          className="cl-btn cl-btn-secondary cl-btn-sm"
          disabled={busy}
          onClick={() => void startSession('assisted')}
        >
          Start assisted session
        </button>
      </div>
      {activeSessionId != null ? (
        <p className="cl-muted">
          Active session id <strong>{activeSessionId}</strong> — mark milestones for this session.
        </p>
      ) : null}
      <div className="cl-btn-row">
        <button
          type="button"
          className="cl-btn cl-btn-sm"
          disabled={busy || activeSessionId == null}
          onClick={() =>
            activeSessionId != null
              ? void patchSession(activeSessionId, { first_meaningful_insight_at: new Date().toISOString() })
              : undefined
          }
        >
          Mark first meaningful insight (now)
        </button>
        <button
          type="button"
          className="cl-btn cl-btn-sm"
          disabled={busy || activeSessionId == null}
          onClick={() =>
            activeSessionId != null
              ? void patchSession(activeSessionId, { completed_at: new Date().toISOString() })
              : undefined
          }
        >
          Mark completed (now)
        </button>
      </div>
      {error ? (
        <p className="cl-msg cl-msg-error" role="alert">
          {error}
        </p>
      ) : null}
      <h4 className="cl-h4">Sessions on this run</h4>
      {sessions.length === 0 ? (
        <p className="cl-muted">No sessions yet.</p>
      ) : (
        <ul className="cl-diagnosis-session-list">
          {sessions.map((s) => {
            const dur =
              s.completed_at != null
                ? (new Date(s.completed_at).getTime() - new Date(s.started_at).getTime()) / 1000
                : null
            const ttfi =
              s.first_meaningful_insight_at != null
                ? (new Date(s.first_meaningful_insight_at).getTime() - new Date(s.started_at).getTime()) /
                  1000
                : null
            return (
              <li key={s.id}>
                <strong>#{s.id}</strong> · {s.mode}
                {s.synthetic ? ' · synthetic' : ''} · duration {fmtSec(dur)} · first insight {fmtSec(ttfi)}
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}
