import type { ConfigScoreComparisonSummary } from '../api/types'
import { formatScoreDeltaPct } from './scoreComparisonFormat'

export function ScoreComparisonDl({ summary }: { summary: ConfigScoreComparisonSummary }) {
  const id = (n: number | null | undefined) => (n == null ? '—' : String(n))
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
        </dd>
      </div>
    </dl>
  )
}
