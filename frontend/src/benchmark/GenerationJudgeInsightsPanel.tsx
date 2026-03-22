import type { RunDetail } from '../api/types'
import { formatUsd } from './dashboardFormat'
import { evaluationScoreRows, extractGenerationJudgeInsights } from './runDiagnosis'

function fmtTok(n: number | null): string {
  if (n == null) return 'N/A'
  return String(n)
}

export function GenerationJudgeInsightsPanel({ runDetail }: { runDetail: RunDetail }) {
  const g = extractGenerationJudgeInsights(runDetail.generation, runDetail.evaluation)
  const scoreRows = evaluationScoreRows(runDetail.evaluation)
  const usedLlmJudge =
    runDetail.evaluation &&
    typeof runDetail.evaluation === 'object' &&
    runDetail.evaluation.used_llm_judge === true

  const hasEvaluation = runDetail.evaluation != null && typeof runDetail.evaluation === 'object'

  return (
    <section className="cl-card cl-diagnosis-panel" data-testid="generation-judge-insights">
      <h3 className="cl-diagnosis-title">Generation &amp; judge</h3>
      <p className="cl-muted">
        Models, tokens, and cost from the run detail payload; parse/retry flags from judge{' '}
        <code>metadata_json</code>. Scores mirror the evaluation row (0–1 where present).
      </p>
      <dl className="cl-dash-dl cl-diagnosis-dl">
        <div className="cl-dash-dl-row">
          <dt>Generation model</dt>
          <dd>{g.generationModel ?? '—'}</dd>
        </div>
        <div className="cl-dash-dl-row">
          <dt>Judge model</dt>
          <dd>
            {g.judgeModel ?? (usedLlmJudge ? '—' : 'N/A (heuristic path — no LLM judge)')}
          </dd>
        </div>
        <div className="cl-dash-dl-row">
          <dt>Gen tokens (in / out)</dt>
          <dd>
            {fmtTok(g.genInputTokens)} / {fmtTok(g.genOutputTokens)}
          </dd>
        </div>
        <div className="cl-dash-dl-row">
          <dt>Judge tokens (in / out)</dt>
          <dd>
            {fmtTok(g.judgeInputTokens)} / {fmtTok(g.judgeOutputTokens)}
          </dd>
        </div>
        <div className="cl-dash-dl-row">
          <dt>Total cost (eval row)</dt>
          <dd>{formatUsd(g.totalCostUsd)}</dd>
        </div>
      </dl>

      <h4 className="cl-diagnosis-subheading">Evaluation scores</h4>
      {hasEvaluation ? (
        <div className="cl-eval-grid cl-diagnosis-eval-grid" data-testid="evaluation-score-grid">
          {scoreRows.map((r) => (
            <div key={r.label} className="cl-eval-row">
              <span className="cl-eval-k">{r.label}</span>
              <span className={r.emphasize ? 'cl-diagnosis-score-strong' : undefined}>{r.value}</span>
            </div>
          ))}
        </div>
      ) : (
        <p className="cl-muted cl-empty-inline">No evaluation row on this run yet.</p>
      )}

      <h4 className="cl-diagnosis-subheading">Parse &amp; retry</h4>
      {!hasEvaluation ? (
        <p className="cl-muted cl-empty-inline">No judge metadata — evaluation not persisted.</p>
      ) : g.badges.length > 0 ? (
        <div className="cl-diagnosis-badges" aria-label="Parse and provider notes">
          {g.badges.map((b) => (
            <span
              key={b.key}
              className={
                b.tone === 'warn' ? 'cl-diagnosis-badge cl-diagnosis-badge--warn' : 'cl-diagnosis-badge'
              }
            >
              {b.label}
            </span>
          ))}
        </div>
      ) : (
        <p className="cl-muted cl-empty-inline">No judge parse warnings on this run.</p>
      )}
    </section>
  )
}
