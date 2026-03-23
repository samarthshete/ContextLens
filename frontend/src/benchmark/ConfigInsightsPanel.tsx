import { useId, useMemo } from 'react'
import type { ConfigInsight } from '../api/types'
import { formatLatencyMs, formatUsd } from './dashboardFormat'
import {
  computeConfigInsightBadgeWinners,
  configInsightRowClasses,
  formatInsightTimestamp,
  formatScore,
  sortConfigInsightsByTracedDesc,
} from './dashboardAnalyticsFormat'

function nameForId(rows: ConfigInsight[], id: number | null): string | null {
  if (id == null) return null
  const row = rows.find((r) => r.pipeline_config_id === id)
  return row ? row.pipeline_config_name : null
}

function InsightBadge({ label, name }: { label: string; name: string | null }) {
  if (name == null) return null
  return (
    <span className="cl-config-insight-badge" role="listitem">
      <span className="cl-config-insight-badge-label">{label}</span>{' '}
      <strong className="cl-config-insight-badge-value">{name}</strong>
    </span>
  )
}

export function ConfigInsightsBucketSection({
  heuristic,
  llm,
}: {
  heuristic: ConfigInsight[]
  llm: ConfigInsight[]
}) {
  const bothEmpty = heuristic.length === 0 && llm.length === 0

  if (bothEmpty) {
    return (
      <section
        className="cl-card"
        aria-label="Config insights"
        data-testid="config-insights"
      >
        <h2>Config insights</h2>
        <p className="cl-muted">
          Split by evaluator bucket — <strong>heuristic</strong> vs <strong>LLM judge</strong>. Average
          scores use only runs in that bucket (no mixing).
        </p>
        <p className="cl-muted cl-empty-inline">No config insights yet.</p>
      </section>
    )
  }

  return (
    <section aria-label="Config insights by evaluator" data-testid="config-insights">
      <div className="cl-card cl-config-insights-intro">
        <h2>Config insights</h2>
        <p className="cl-muted">
          Split by evaluator bucket — <strong>heuristic</strong> vs <strong>LLM judge</strong>. Each table
          averages scores and costs only over runs evaluated in that bucket (
          <code>analytics.config_insights.heuristic</code> / <code>.llm</code>).
        </p>
      </div>
      <ConfigInsightsPanel
        title="Heuristic evaluation"
        bucketTestId="config-insights-heuristic"
        data={heuristic}
      />
      <ConfigInsightsPanel
        title="LLM judge evaluation"
        bucketTestId="config-insights-llm"
        data={llm}
      />
    </section>
  )
}

type ConfigInsightsPanelProps = {
  title: string
  bucketTestId: string
  data: ConfigInsight[]
}

export function ConfigInsightsPanel({ title, bucketTestId, data }: ConfigInsightsPanelProps) {
  const headingId = useId()
  const sorted = useMemo(() => sortConfigInsightsByTracedDesc(data), [data])
  const winners = useMemo(() => computeConfigInsightBadgeWinners(data), [data])

  const fastestName = nameForId(data, winners.fastestConfigId)
  const mostUsedName = nameForId(data, winners.mostUsedConfigId)
  const highestRelName = nameForId(data, winners.highestRelevanceConfigId)
  const failProneName = nameForId(data, winners.mostFailureProneConfigId)
  const cheapestName = nameForId(data, winners.cheapestConfigId)

  const hasBadgeRow =
    fastestName != null ||
    mostUsedName != null ||
    highestRelName != null ||
    failProneName != null ||
    (winners.showCheapestBadge && cheapestName != null)

  if (data.length === 0) {
    return (
      <section
        className="cl-card cl-config-insights-bucket-panel"
        aria-labelledby={headingId}
        data-testid={bucketTestId}
      >
        <h3 id={headingId}>{title}</h3>
        <p className="cl-muted cl-empty-inline">No traced runs in this evaluator bucket yet.</p>
      </section>
    )
  }

  return (
    <section
      className="cl-card cl-config-insights-bucket-panel"
      aria-labelledby={headingId}
      data-testid={bucketTestId}
    >
      <h3 id={headingId}>{title}</h3>
      <p className="cl-muted">
        From <code>dashboard-analytics</code> — per-pipeline performance, quality, cost, and failures
        (sorted by traced runs). Only runs whose evaluation row is in this bucket.
      </p>

      {hasBadgeRow ? (
        <div className="cl-config-insight-badges" role="list" aria-label="Config highlights">
          <InsightBadge label="Fastest (avg total latency)" name={fastestName} />
          <InsightBadge label="Most used (traced runs)" name={mostUsedName} />
          <InsightBadge label="Highest relevance" name={highestRelName} />
          <InsightBadge label="Most failure-prone (failed runs)" name={failProneName} />
          {winners.showCheapestBadge ? (
            <InsightBadge label="Cheapest (avg cost)" name={cheapestName} />
          ) : null}
        </div>
      ) : null}

      <div className="cl-table-wrap cl-config-insights-table-wrap">
        <table className="cl-table cl-config-insights-table">
          <thead>
            <tr>
              <th>Config</th>
              <th>Traced runs</th>
              <th>Completed</th>
              <th>Failed</th>
              <th>Avg total latency</th>
              <th>Avg retrieval relevance</th>
              <th>Avg completeness</th>
              <th>Avg context coverage</th>
              <th>Avg faithfulness</th>
              <th>Avg cost</th>
              <th>Total cost</th>
              <th>Top failure type</th>
              <th>Latest run</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((c) => {
              return (
                <tr
                  key={c.pipeline_config_id}
                  className={configInsightRowClasses(c.pipeline_config_id, winners)}
                >
                  <td>
                    <span className="cl-config-insight-name">{c.pipeline_config_name}</span>
                    <span className="cl-muted cl-config-insight-id"> #{c.pipeline_config_id}</span>
                  </td>
                  <td>{c.traced_runs}</td>
                  <td>{c.completed_runs}</td>
                  <td>{c.failed_runs}</td>
                  <td>{formatLatencyMs(c.avg_total_latency_ms)}</td>
                  <td>{formatScore(c.avg_retrieval_relevance)}</td>
                  <td>{formatScore(c.avg_completeness)}</td>
                  <td>{formatScore(c.avg_context_coverage)}</td>
                  <td>{formatScore(c.avg_faithfulness)}</td>
                  <td>{formatUsd(c.avg_cost_usd)}</td>
                  <td>{formatUsd(c.total_cost_usd)}</td>
                  <td className="cl-td-wrap">{c.top_failure_type ?? '—'}</td>
                  <td className="cl-td-wrap cl-tabular-nums">{formatInsightTimestamp(c.latest_run_at)}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </section>
  )
}
