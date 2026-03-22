import type { FailureAnalysisSection } from '../api/types'
import { failureTypeBarPercents, formatPercent, sortedFailureCounts } from './dashboardAnalyticsFormat'

function formatWhen(iso: string): string {
  try {
    return new Date(iso).toLocaleString()
  } catch {
    return iso
  }
}

export function FailureBreakdownPanel({
  data,
  onOpenRunDetail,
}: {
  data: FailureAnalysisSection
  onOpenRunDetail?: (runId: number) => void
}) {
  const sorted = sortedFailureCounts(data.overall_counts)
  const totalFailures = sorted.reduce((s, [, c]) => s + c, 0)
  const isEmpty = totalFailures === 0

  return (
    <section className="cl-card" aria-label="Failure breakdown" data-testid="failure-breakdown">
      <h2>Failure Breakdown</h2>
      <p className="cl-muted">
        From <code>analytics.failure_analysis</code> — <code>overall_counts</code> and{' '}
        <code>overall_percentages</code>.
      </p>

      {isEmpty ? (
        <p className="cl-muted cl-empty-inline">No failures recorded.</p>
      ) : (
        <>
          <h3 className="cl-failure-overall-heading">Overall</h3>
          <div className="cl-failure-bars" data-testid="failure-overall-bars" aria-label="Failure types by share">
            {failureTypeBarPercents(sorted, totalFailures).map(({ failureType, count, barPct }) => (
              <div key={failureType} className="cl-failure-bar-row">
                <span className="cl-failure-bar-type" title={failureType}>
                  {failureType}
                </span>
                <div className="cl-failure-bar-track">
                  <div className="cl-failure-bar-fill" style={{ width: `${barPct}%` }} />
                </div>
                <span className="cl-failure-bar-count">
                  {count} ({formatPercent(data.overall_percentages[failureType])})
                </span>
              </div>
            ))}
          </div>
          <div className="cl-table-wrap">
            <table className="cl-table">
              <thead>
                <tr>
                  <th>Failure type</th>
                  <th>Count</th>
                  <th>%</th>
                </tr>
              </thead>
              <tbody>
                {sorted.map(([ft, count]) => (
                  <tr key={ft}>
                    <td>
                      <strong>{ft}</strong>
                    </td>
                    <td>{count}</td>
                    <td>{formatPercent(data.overall_percentages[ft])}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="cl-muted cl-failure-total-note">{totalFailures} failure label(s) total.</p>
        </>
      )}

      {!isEmpty && data.by_config.length > 0 ? (
        <>
          <h3>By pipeline config</h3>
          <div className="cl-table-wrap">
            <table className="cl-table">
              <thead>
                <tr>
                  <th>Config</th>
                  <th>Total failures</th>
                  <th>Top types</th>
                </tr>
              </thead>
              <tbody>
                {data.by_config.map((cfg) => {
                  const top = sortedFailureCounts(cfg.failure_counts)
                    .slice(0, 3)
                    .map(([k, v]) => `${k}: ${v}`)
                    .join('; ')
                  return (
                    <tr key={cfg.pipeline_config_id}>
                      <td>
                        {cfg.pipeline_config_name} (#{cfg.pipeline_config_id})
                      </td>
                      <td>{cfg.total_failures}</td>
                      <td className="cl-td-wrap">{top || '—'}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </>
      ) : null}

      {!isEmpty && data.recent_failed_runs.length > 0 ? (
        <>
          <h3>Recent failed runs</h3>
          <div className="cl-table-wrap">
            <table className="cl-table">
              <thead>
                <tr>
                  <th>Run ID</th>
                  <th>When</th>
                  <th>Failure</th>
                  <th>Config</th>
                  {onOpenRunDetail ? <th /> : null}
                </tr>
              </thead>
              <tbody>
                {data.recent_failed_runs.map((r) => (
                  <tr key={r.run_id}>
                    <td>{r.run_id}</td>
                    <td>{formatWhen(r.created_at)}</td>
                    <td>{r.failure_type ?? '—'}</td>
                    <td>#{r.pipeline_config_id}</td>
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
        </>
      ) : null}
    </section>
  )
}
