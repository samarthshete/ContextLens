import type { RunDetail } from '../api/types'
import { computeRetrievalDiagnosis } from './runDiagnosis'

export function RetrievalDiagnosisPanel({ runDetail }: { runDetail: RunDetail }) {
  const d = computeRetrievalDiagnosis(runDetail.retrieval_hits)

  return (
    <section className="cl-card cl-diagnosis-panel" data-testid="retrieval-diagnosis">
      <h3 className="cl-diagnosis-title">Retrieval diagnosis</h3>
      <p className="cl-muted">
        Quick read on <strong>how many</strong> chunks came back, <strong>how confident</strong> the top
        match is, and whether <strong>#1 vs #2</strong> are separated.
      </p>
      <dl className="cl-dash-dl cl-diagnosis-dl">
        <div className="cl-dash-dl-row">
          <dt>Hits returned</dt>
          <dd>{d.hitCount}</dd>
        </div>
        <div className="cl-dash-dl-row">
          <dt>Top hit score</dt>
          <dd>{d.topScore != null ? d.topScore.toFixed(4) : 'N/A'}</dd>
        </div>
        <div className="cl-dash-dl-row">
          <dt>Rank 1 − rank 2</dt>
          <dd>{d.rank1MinusRank2 != null ? d.rank1MinusRank2.toFixed(4) : 'N/A'}</dd>
        </div>
      </dl>
      <ul className="cl-diagnosis-list">
        {d.interpretations.map((t, i) => (
          <li key={i}>{t}</li>
        ))}
      </ul>
    </section>
  )
}
