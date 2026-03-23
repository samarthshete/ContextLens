import type { ConfigComparisonMetrics, ConfigScoreComparisonSummary } from '../api/types'
import { completenessAbsSpreadFromMetrics, formatScoreDeltaPct } from './scoreComparisonFormat'

export function ScoreComparisonDl({
  summary,
  metricsRows,
}: {
  summary: ConfigScoreComparisonSummary
  /** When provided, used to detect negligible completeness spread (caveat only). */
  metricsRows?: ConfigComparisonMetrics[]
}) {
  const id = (n: number | null | undefined) => (n == null ? '—' : String(n))
  const compSpread =
    metricsRows != null && metricsRows.length > 0
      ? completenessAbsSpreadFromMetrics(metricsRows, summary)
      : null
  const completenessCaveat = compSpread != null && compSpread < 0.02

  return (
    <dl className="cl-dash-dl cl-score-comparison-dl">
      <div className="cl-dash-dl-row">
        <dt>Faithfulness — best / worst config</dt>
        <dd>
          {id(summary.best_config_faithfulness)} / {id(summary.worst_config_faithfulness)} · Δ{' '}
          {formatScoreDeltaPct(summary.faithfulness_delta_pct)}{' '}
          <span className="cl-muted">
            (100×(best−worst)/worst avg; N/A if worst ≤ 0; faithfulness N/A when heuristic+LLM merged)
          </span>
        </dd>
      </div>
      <div className="cl-dash-dl-row">
        <dt>Completeness — best / worst config</dt>
        <dd>
          {id(summary.best_config_completeness)} / {id(summary.worst_config_completeness)} · Δ{' '}
          {formatScoreDeltaPct(summary.completeness_delta_pct)}
          <span className="cl-muted">
            {' '}
            (often a weak differentiator; prefer retrieval relevance and failure-type mix when tradeoffs
            are close.)
          </span>
          {completenessCaveat ? (
            <span className="cl-score-comparison-caveat" data-testid="completeness-small-delta-caveat">
              {' '}
              Completeness difference is small on this dataset.
            </span>
          ) : null}
        </dd>
      </div>
    </dl>
  )
}
