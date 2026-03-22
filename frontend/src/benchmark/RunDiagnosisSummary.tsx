import type { RunDetail } from '../api/types'
import {
  computeContextQuality,
  computeRetrievalDiagnosis,
  computeRunDiagnosisSummary,
  extractGenerationJudgeInsights,
} from './runDiagnosis'

export function RunDiagnosisSummary({ runDetail }: { runDetail: RunDetail }) {
  const retrieval = computeRetrievalDiagnosis(runDetail.retrieval_hits)
  const contextQ = computeContextQuality(runDetail.retrieval_hits, runDetail.pipeline_config.top_k)
  const genJudge = extractGenerationJudgeInsights(runDetail.generation, runDetail.evaluation)
  const lines = computeRunDiagnosisSummary(runDetail, retrieval, contextQ, genJudge)

  return (
    <section className="cl-card cl-diagnosis-summary" data-testid="run-diagnosis-summary">
      <h3 className="cl-diagnosis-title">Run diagnosis summary</h3>
      <p className="cl-muted">
        One-glance hypotheses from retrieval shape, context heuristics, scores, and cost — not a
        substitute for reading the full evaluation.
      </p>
      <ul className="cl-diagnosis-summary-list">
        {lines.map((line) => (
          <li
            key={line.key}
            className={
              line.severity === 'attention'
                ? 'cl-diagnosis-summary-li cl-diagnosis-summary-li--attention'
                : 'cl-diagnosis-summary-li'
            }
          >
            {line.text}
          </li>
        ))}
      </ul>
    </section>
  )
}
