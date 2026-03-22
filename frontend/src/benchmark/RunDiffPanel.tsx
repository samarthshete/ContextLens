import { useCallback, useMemo, useState } from 'react'
import { api } from '../api/client'
import type { RunDetail } from '../api/types'
import { describeApiError } from './errorMessage'
import { buildRunDiffModel, verdictLabel, type DiffVerdict } from './runDiff'

function verdictClass(v: DiffVerdict): string {
  switch (v) {
    case 'improved':
      return 'cl-run-diff-verdict cl-run-diff-verdict--improved'
    case 'worse':
      return 'cl-run-diff-verdict cl-run-diff-verdict--worse'
    case 'same':
      return 'cl-run-diff-verdict cl-run-diff-verdict--same'
    default:
      return 'cl-run-diff-verdict cl-run-diff-verdict--unknown'
  }
}

export function RunDiffPanel({ baseRun }: { baseRun: RunDetail }) {
  const [compareInput, setCompareInput] = useState('')
  const [compareRun, setCompareRun] = useState<RunDetail | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const model = useMemo(
    () => (compareRun ? buildRunDiffModel(baseRun, compareRun) : null),
    [baseRun, compareRun],
  )

  const loadCompare = useCallback(async () => {
    const raw = compareInput.trim()
    const n = Number.parseInt(raw, 10)
    if (!Number.isFinite(n) || n <= 0 || !Number.isInteger(n)) {
      setError('Enter a positive integer run ID to compare.')
      setCompareRun(null)
      return
    }
    if (n === baseRun.run_id) {
      setError('Pick a different run ID than the one you are viewing.')
      setCompareRun(null)
      return
    }
    setLoading(true)
    setError(null)
    try {
      const d = await api.getRun(n)
      setCompareRun(d)
    } catch (e) {
      setCompareRun(null)
      setError(describeApiError(e))
    } finally {
      setLoading(false)
    }
  }, [compareInput, baseRun.run_id])

  return (
    <section className="cl-card cl-run-diff" data-testid="run-diff-panel">
      <h3 className="cl-diagnosis-title">Compare runs</h3>
      <p className="cl-muted">
        Load another run by ID using the same <code>GET /runs/&#123;id&#125;</code> data as this page.
        <strong> Run A</strong> is the run you opened; <strong>Run B</strong> is the comparison target.
      </p>

      <div className="cl-field cl-run-diff-field">
        <label htmlFor="run-diff-other-id">Compare with run ID</label>
        <div className="cl-run-diff-actions">
          <input
            id="run-diff-other-id"
            type="text"
            inputMode="numeric"
            placeholder="e.g. 102"
            value={compareInput}
            onChange={(ev) => {
              setCompareInput(ev.target.value)
              setError(null)
            }}
            onKeyDown={(ev) => {
              if (ev.key === 'Enter') void loadCompare()
            }}
          />
          <button
            type="button"
            className="cl-btn cl-btn-secondary cl-btn-sm"
            disabled={loading}
            onClick={() => void loadCompare()}
          >
            {loading ? 'Loading…' : 'Load comparison'}
          </button>
        </div>
      </div>

      {error ? (
        <p className="cl-msg cl-msg-error" role="alert">
          {error}
        </p>
      ) : null}

      {model ? (
        <>
          {model.warnings.length > 0 ? (
            <ul className="cl-run-diff-warnings">
              {model.warnings.map((w, i) => (
                <li key={i}>{w}</li>
              ))}
            </ul>
          ) : null}

          <div className="cl-run-diff-summary" data-testid="run-diff-summary">
            <h4 className="cl-diagnosis-subheading">Summary</h4>
            <ul className="cl-diagnosis-list">
              {model.summaryLines.map((line, i) => (
                <li key={i}>{line}</li>
              ))}
            </ul>
          </div>

          <div className="cl-table-wrap cl-run-diff-table-wrap">
            <table className="cl-table cl-run-diff-table">
              <thead>
                <tr>
                  <th>Metric</th>
                  <th>
                    Run A <span className="cl-muted">(#{model.baseRunId})</span>
                  </th>
                  <th>
                    Run B <span className="cl-muted">(#{model.compareRunId})</span>
                  </th>
                  <th>vs A</th>
                </tr>
              </thead>
              <tbody>
                {model.rows.map((row) => (
                  <tr key={row.id}>
                    <td>{row.label}</td>
                    <td className="cl-td-wrap">{row.aValue}</td>
                    <td className="cl-td-wrap">{row.bValue}</td>
                    <td>
                      <span className={verdictClass(row.verdict)}>{verdictLabel(row.verdict)}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      ) : !loading && !error ? (
        <p className="cl-muted cl-empty-inline">Enter a run ID and load to see a side-by-side diff.</p>
      ) : null}
    </section>
  )
}
