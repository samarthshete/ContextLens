import type { TimeSeriesDay } from '../api/types'
import { formatDate, timeSeriesDayStack, timeSeriesMaxRuns } from './dashboardAnalyticsFormat'
import { formatLatencyMs, formatUsd } from './dashboardFormat'

export type DashboardTrendPanelProps = {
  /** True while a refresh is in flight and prior analytics are still shown. */
  isRefreshing: boolean
  /** `analytics.time_series` from GET /api/v1/runs/dashboard-analytics */
  timeSeries: TimeSeriesDay[]
  /** e.g. dataset name — trends are scoped to `dataset_id` on the analytics request */
  datasetSummary?: string | null
}

function TrendStackedBar({ day }: { day: TimeSeriesDay }) {
  const stack = timeSeriesDayStack(day)
  const label = `${day.date}: ${day.runs} run(s), ${day.completed} completed, ${day.failed} system-failed`
  if (day.runs <= 0) {
    return <div className="cl-dash-trend-bar-track cl-dash-trend-bar-track--empty" aria-hidden />
  }
  return (
    <div
      className="cl-dash-trend-bar-track"
      role="img"
      aria-label={label}
      title={`${day.completed} completed · ${day.failed} failed · ${Math.max(0, day.runs - day.completed - day.failed)} other/in progress`}
    >
      {stack.map((seg) =>
        seg.pctOfRuns > 0 ? (
          <div
            key={seg.key}
            className={`cl-dash-trend-seg cl-dash-trend-seg--${seg.key}`}
            style={{ width: `${seg.pctOfRuns}%` }}
          />
        ) : null,
      )}
    </div>
  )
}

/**
 * Run trends from dashboard analytics — stacked daily bars + numeric table.
 */
export function DashboardTrendPanel({
  isRefreshing,
  timeSeries,
  datasetSummary,
}: DashboardTrendPanelProps) {
  const maxRuns = timeSeriesMaxRuns(timeSeries)

  if (isRefreshing && timeSeries.length === 0) {
    return (
      <section
        className="cl-card"
        aria-label="Run trends"
        aria-busy="true"
        data-testid="dashboard-run-trends"
      >
        <h2>Run Trends</h2>
        <p className="cl-muted">
          From <code>GET /api/v1/runs/dashboard-analytics</code> — <code>time_series</code>.
        </p>
        <p className="cl-loading" aria-live="polite">
          Loading run trends…
        </p>
      </section>
    )
  }

  if (!isRefreshing && timeSeries.length === 0) {
    return (
      <section className="cl-card" aria-label="Run trends">
        <h2>Run Trends</h2>
        {datasetSummary ? (
          <p className="cl-muted" data-testid="dashboard-trends-dataset-scope">
            Scoped to {datasetSummary}.
          </p>
        ) : null}
        <p className="cl-muted">
          From <code>GET /api/v1/runs/dashboard-analytics</code> — <code>time_series</code>.
        </p>
        <p className="cl-muted cl-empty-inline">
          No daily trend rows yet (no runs in the analytics window).
        </p>
      </section>
    )
  }

  return (
    <section
      className="cl-card"
      aria-label="Run trends"
      aria-busy={isRefreshing}
      data-testid="dashboard-run-trends"
    >
      <div className="cl-dash-header-row">
        <h2>Run Trends</h2>
        {isRefreshing ? (
          <span className="cl-muted cl-loading-inline" aria-live="polite">
            Updating…
          </span>
        ) : null}
      </div>
      {datasetSummary ? (
        <p className="cl-muted" data-testid="dashboard-trends-dataset-scope">
          Scoped to {datasetSummary} (<code>?dataset_id=</code> on dashboard API calls).
        </p>
      ) : null}
      <p className="cl-muted">
        From <code>GET /api/v1/runs/dashboard-analytics</code> — <code>time_series</code> (
        {timeSeries.length} day{timeSeries.length !== 1 ? 's' : ''}). Bar = daily run volume (max day{' '}
        <strong>{maxRuns}</strong>); green = completed, red = system failures (run <code>status</code>), neutral
        = other/in progress. Exact counts stay in the table.
      </p>
      <div className="cl-dash-trend-legend" aria-hidden>
        <span className="cl-dash-trend-legend-item">
          <span className="cl-dash-trend-legend-swatch cl-dash-trend-seg--completed" /> Completed
        </span>
        <span className="cl-dash-trend-legend-item">
          <span className="cl-dash-trend-legend-swatch cl-dash-trend-seg--failed" /> System failures
        </span>
        <span className="cl-dash-trend-legend-item">
          <span className="cl-dash-trend-legend-swatch cl-dash-trend-seg--other" /> Other / in progress
        </span>
      </div>

      <div className="cl-dash-trends-chart" data-testid="dashboard-trends-chart">
        {timeSeries.map((d) => (
          <div key={d.date} className="cl-dash-trend-row">
            <span className="cl-dash-trend-date">{formatDate(d.date)}</span>
            <TrendStackedBar day={d} />
            <span
              className="cl-dash-trend-meta"
              title={`${d.completed} completed, ${d.failed} system failures`}
            >
              {d.runs} runs
            </span>
          </div>
        ))}
      </div>

      <h3 className="cl-dash-trends-table-heading">Daily numbers</h3>
      <div className="cl-table-wrap">
        <table className="cl-table">
          <thead>
            <tr>
              <th>Date</th>
              <th>Runs</th>
              <th>Completed</th>
              <th>System failures</th>
              <th>Avg total latency (ms)</th>
              <th>Avg cost (USD)</th>
            </tr>
          </thead>
          <tbody>
            {timeSeries.map((d) => (
              <tr key={d.date}>
                <td>{d.date}</td>
                <td>{d.runs}</td>
                <td>{d.completed}</td>
                <td>{d.failed}</td>
                <td>{formatLatencyMs(d.avg_total_latency_ms)}</td>
                <td>{formatUsd(d.avg_cost_usd)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
