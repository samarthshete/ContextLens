import type { RunDetail } from '../api/types'
import { ContextQualityPanel } from './ContextQualityPanel'
import {
  DiagnosisTimingExperimentPanel,
  type DiagnosisExperimentMode,
} from './DiagnosisTimingExperimentPanel'
import { triggerBrowserDownload, runTraceExportFilename, serializeRunTraceJson } from './exportDownload'
import { GenerationJudgeInsightsPanel } from './GenerationJudgeInsightsPanel'
import { PhaseTimeline } from './PhaseTimeline'
import { RetrievalDiagnosisPanel } from './RetrievalDiagnosisPanel'
import { RetrievalHitsSection } from './RetrievalHitsSection'
import { RunDiagnosisSummary } from './RunDiagnosisSummary'
import { RunDiffPanel } from './RunDiffPanel'
import { RunQueuePanel } from './RunQueuePanel'
import { FailureBadge, MetricCard, ScoreBadge, SectionHeader, StatusBadge, TracePanel } from './ui'

function formatJson(v: unknown): string {
  return JSON.stringify(v, null, 2)
}

function formatWhen(iso: string): string {
  try {
    return new Date(iso).toLocaleString()
  } catch {
    return iso
  }
}

function runStageLabel(status: string): string {
  switch (status) {
    case 'pending':
      return 'Queued'
    case 'running':
      return 'Retrieving...'
    case 'retrieval_completed':
      return 'Generating answer...'
    case 'generation_completed':
      return 'Running LLM judge...'
    case 'completed':
      return 'Finished'
    case 'failed':
      return 'Failed'
    default:
      return status
  }
}

function numericEval(ev: Record<string, unknown> | null, key: string): number | null {
  const raw = ev?.[key]
  return typeof raw === 'number' && Number.isFinite(raw) ? raw : null
}

function averageJudgeScore(ev: Record<string, unknown> | null): number | null {
  const values = ['faithfulness', 'completeness', 'retrieval_relevance', 'context_coverage', 'groundedness']
    .map((key) => numericEval(ev, key))
    .filter((value): value is number => value != null)
  if (!values.length) return null
  return values.reduce((sum, value) => sum + value, 0) / values.length
}

function failureType(ev: Record<string, unknown> | null): string | null {
  const raw = ev?.failure_type
  return typeof raw === 'string' ? raw : null
}

function recommendedFix(runDetail: RunDetail): string {
  const failure = failureType(runDetail.evaluation)
  if (!failure || failure === 'NO_FAILURE') {
    return 'No failure label on this run. Use the retrieved evidence and judge scores to confirm the answer stays grounded.'
  }
  if (failure.includes('RETRIEVAL')) {
    return 'Tune retrieval first: inspect top chunks, adjust chunking/top_k, and add source coverage for the missing facts.'
  }
  if (failure.includes('HALLUCINATION') || failure.includes('FAITHFULNESS')) {
    return 'Tighten generation: require citations from retrieved context and lower tolerance for unsupported claims.'
  }
  if (failure.includes('INCOMPLETE') || failure.includes('COMPLETENESS')) {
    return 'Improve answer completeness: expand retrieval coverage or prompt the model to answer all parts of the query.'
  }
  return 'Compare this trace with a passing run, then fix the first weak stage: retrieval relevance, context coverage, or judge score.'
}

function primaryFailureReason(runDetail: RunDetail): string {
  const failure = failureType(runDetail.evaluation)
  const judgeScore = averageJudgeScore(runDetail.evaluation)
  if (!failure || failure === 'NO_FAILURE') {
    return judgeScore == null
      ? 'No failure label or judge average is available yet.'
      : `No failure label. Judge average is ${Math.round(judgeScore * 100)}%.`
  }
  if (failure.includes('RETRIEVAL')) {
    return 'The retrieved context is likely missing, weak, or not specific enough for the query.'
  }
  if (failure.includes('HALLUCINATION') || failure.includes('FAITHFULNESS')) {
    return 'The answer appears to include claims that are not grounded in retrieved evidence.'
  }
  if (failure.includes('INCOMPLETE') || failure.includes('COMPLETENESS')) {
    return 'The answer likely covers only part of the expected response.'
  }
  return 'The LLM judge or heuristic evaluator found a quality issue that needs trace-level inspection.'
}

function TraceStep({
  label,
  value,
  detail,
}: {
  label: string
  value: string
  detail?: string
}) {
  return (
    <div className="cl-trace-step">
      <span>{label}</span>
      <strong>{value}</strong>
      {detail ? <small>{detail}</small> : null}
    </div>
  )
}

function EvaluationStructured({ ev }: { ev: Record<string, unknown> | null }) {
  if (!ev || typeof ev !== 'object') {
    return <p className="cl-muted">No evaluation row.</p>
  }
  const meta = ev.metadata_json as Record<string, unknown> | null | undefined

  return (
    <div className="cl-eval-grid">
      {(
        [
        ['Faithfulness', ev.faithfulness],
        ['Completeness', ev.completeness],
        ['Retrieval relevance', ev.retrieval_relevance],
        ['Context coverage', ev.context_coverage],
        ['Groundedness', ev.groundedness],
        ] satisfies Array<[string, unknown]>
      ).map(([label, value]) => (
        <div key={label} className="cl-eval-row">
          <span className="cl-eval-k">{label}</span>
          <span>{value != null ? String(value) : '-'}</span>
        </div>
      ))}
      <div className="cl-eval-row">
        <span className="cl-eval-k">Failure type</span>
        <FailureBadge failureType={failureType(ev)} />
      </div>
      <div className="cl-eval-row">
        <span className="cl-eval-k">LLM judge</span>
        <span>{ev.used_llm_judge === true ? 'yes' : ev.used_llm_judge === false ? 'no' : '-'}</span>
      </div>
      <div className="cl-eval-row">
        <span className="cl-eval-k">Est. cost USD</span>
        <span>{ev.cost_usd != null ? String(ev.cost_usd) : '-'}</span>
      </div>
      {meta && Object.keys(meta).length > 0 ? (
        <details className="cl-details">
          <summary>Judge &amp; parse metadata</summary>
          <dl className="cl-meta-dl">
            {Object.entries(meta).map(([k, v]) => (
              <div key={k}>
                <dt>{k}</dt>
                <dd>{typeof v === 'object' ? formatJson(v) : String(v)}</dd>
              </div>
            ))}
          </dl>
        </details>
      ) : null}
    </div>
  )
}

export function RunDetailView({
  routeRunId,
  detailRunId,
  runDetail,
  detailLoading,
  diagnosisExperimentMode,
  documentTitleById,
  onRunIdInputChange,
  onDiagnosisModeChange,
}: {
  routeRunId?: string
  detailRunId: number | null
  runDetail: RunDetail | null
  detailLoading: boolean
  diagnosisExperimentMode: DiagnosisExperimentMode
  documentTitleById: Map<number, string>
  onRunIdInputChange: (raw: string) => void
  onDiagnosisModeChange: (mode: DiagnosisExperimentMode) => void
}) {
  const judgeScore = runDetail ? averageJudgeScore(runDetail.evaluation) : null
  const failure = runDetail ? failureType(runDetail.evaluation) : null
  const topHit = runDetail?.retrieval_hits[0]

  return (
    <section className="cl-card cl-trace-view">
      <SectionHeader
        eyebrow="Trace detail"
        title="Run Trace Diagnosis"
        description="Inspect the query, retrieved evidence, generated answer, judge score, failure label, latency, and recommended fix."
        actions={
          runDetail ? (
            <button
              type="button"
              className="cl-btn cl-btn-secondary cl-btn-sm"
              data-testid="run-export-json"
              onClick={() => {
                triggerBrowserDownload(
                  runTraceExportFilename(runDetail.run_id),
                  serializeRunTraceJson(runDetail),
                  'application/json',
                )
              }}
            >
              Export JSON
            </button>
          ) : null
        }
      />

      <div className="cl-field cl-trace-id-field">
        <label htmlFor="rid">Run ID</label>
        <input
          id="rid"
          type="text"
          inputMode="numeric"
          placeholder="e.g. 42"
          value={detailRunId ?? ''}
          onChange={(ev) => onRunIdInputChange(ev.target.value)}
        />
      </div>

      {routeRunId != null && (detailRunId == null || !Number.isFinite(detailRunId)) ? (
        <p className="cl-msg cl-msg-error" role="alert">
          Invalid run ID: &quot;{routeRunId}&quot;. Run IDs must be positive integers.
        </p>
      ) : detailLoading ? (
        <p className="cl-loading">Loading run...</p>
      ) : runDetail ? (
        <>
          <section className="cl-trace-hero" aria-label="Trace summary">
            <div className="cl-trace-hero-main">
              <div className="cl-trace-hero-badges">
                <StatusBadge status={runDetail.status} />
                <FailureBadge failureType={failure} />
                <ScoreBadge score={judgeScore} label="judge avg" />
              </div>
              <h3>Run #{runDetail.run_id}</h3>
              <p>
                <strong>{runStageLabel(runDetail.status)}</strong> · {runDetail.evaluator_type} evaluator · created{' '}
                {formatWhen(runDetail.created_at)}
              </p>
              <p className="cl-trace-failure-reason">{primaryFailureReason(runDetail)}</p>
              {runDetail.status !== 'completed' && runDetail.status !== 'failed' ? (
                <span className="cl-pulse" aria-live="polite">
                  Updating...
                </span>
              ) : null}
            </div>
            <div className="cl-trace-hero-metrics">
              <MetricCard label="Total latency" value={runDetail.total_latency_ms ?? '-'} detail="ms" />
              <MetricCard label="Retrieval" value={runDetail.retrieval_hits.length} detail="chunks returned" />
              <MetricCard label="Top hit score" value={topHit ? topHit.score.toFixed(3) : '-'} detail="rank #1" />
            </div>
          </section>

          <section className="cl-trace-path" aria-label="RAG trace path">
            <TraceStep
              label="1. Query"
              value={`case #${runDetail.query_case.id}`}
              detail={runDetail.query_case.query_text.slice(0, 72)}
            />
            <TraceStep
              label="2. Retrieval"
              value={`${runDetail.retrieval_hits.length} chunks`}
              detail={topHit ? `top score ${topHit.score.toFixed(3)}` : 'no hits'}
            />
            <TraceStep
              label="3. Generation"
              value={runDetail.generation ? 'answer persisted' : 'not persisted'}
              detail={runDetail.generation ? 'full RAG path' : 'heuristic path'}
            />
            <TraceStep
              label="4. Judge"
              value={judgeScore == null ? 'N/A' : `${Math.round(judgeScore * 100)}%`}
              detail={failure || 'NO_FAILURE'}
            />
          </section>

          <section className="cl-trace-diagnosis-card" aria-label="Recommended fix">
            <div>
              <p className="cl-eyebrow">Recommended fix</p>
              <h3>{failure && failure !== 'NO_FAILURE' ? failure.replace(/_/g, ' ') : 'Verify groundedness'}</h3>
            </div>
            <p>{recommendedFix(runDetail)}</p>
          </section>

          <section className="cl-trace-brief">
            <TracePanel title="Query" meta={`case #${runDetail.query_case.id}`}>
              <p className="cl-trace-question">{runDetail.query_case.query_text}</p>
              {runDetail.query_case.expected_answer ? (
                <p className="cl-muted">
                  Expected: <strong>{runDetail.query_case.expected_answer}</strong>
                </p>
              ) : null}
            </TracePanel>
            <TracePanel title="Generated answer" meta={runDetail.generation ? 'full RAG' : 'heuristic path'}>
              {runDetail.generation && typeof runDetail.generation.answer_text === 'string' ? (
                <p className="cl-trace-answer">{String(runDetail.generation.answer_text)}</p>
              ) : runDetail.generation ? (
                <pre className="cl-pre">{formatJson(runDetail.generation)}</pre>
              ) : (
                <p className="cl-muted">No generation persisted for this run.</p>
              )}
            </TracePanel>
          </section>

          <PhaseTimeline runDetail={runDetail} />

          <DiagnosisTimingExperimentPanel runId={runDetail.run_id} onModeChange={onDiagnosisModeChange} />

          {diagnosisExperimentMode === 'manual' ? (
            <p className="cl-msg cl-msg-warn" role="note">
              Manual baseline mode: assisted diagnosis summaries and panels are hidden while you time unaided triage.
            </p>
          ) : (
            <RunDiagnosisSummary runDetail={runDetail} />
          )}

          {runDetail.run_id === detailRunId ? (
            <RunQueuePanel key={runDetail.run_id} runId={runDetail.run_id} runStatus={runDetail.status} />
          ) : null}

          <section className="cl-subsection">
            <h3>Pipeline config</h3>
            <p>
              <strong>{runDetail.pipeline_config.name}</strong> (id {runDetail.pipeline_config.id}) ·{' '}
              {runDetail.pipeline_config.embedding_model} · {runDetail.pipeline_config.chunk_strategy} · top_k{' '}
              {runDetail.pipeline_config.top_k}
            </p>
          </section>

          {diagnosisExperimentMode !== 'manual' ? (
            <div className="cl-diagnosis-stack">
              <RetrievalDiagnosisPanel runDetail={runDetail} />
              <ContextQualityPanel runDetail={runDetail} />
            </div>
          ) : null}

          <RetrievalHitsSection hits={runDetail.retrieval_hits} documentTitleById={documentTitleById} />

          {diagnosisExperimentMode !== 'manual' ? <GenerationJudgeInsightsPanel runDetail={runDetail} /> : null}

          <RunDiffPanel baseRun={runDetail} />

          <section className="cl-subsection">
            <h3>Evaluation</h3>
            <EvaluationStructured ev={runDetail.evaluation} />
            <details className="cl-details">
              <summary>Raw evaluation JSON (debug)</summary>
              <pre className="cl-pre">{formatJson(runDetail.evaluation)}</pre>
            </details>
          </section>
        </>
      ) : (
        <p className="cl-muted">Enter a run id or open a row from “Recent runs”.</p>
      )}
    </section>
  )
}
