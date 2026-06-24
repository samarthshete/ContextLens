import type { ConfigComparisonMetrics, ConfigComparisonResponse, PipelineConfig } from '../api/types'
import { ScoreComparisonDl } from './scoreComparisonDisplay'
import { DataTable, EmptyState, FailureBadge, MetricCard, SectionHeader } from './ui'

function topFailureString(row: ConfigComparisonMetrics): string {
  const top = Object.entries(row.failure_type_counts || {})
    .filter(([key]) => key !== 'NO_FAILURE')
    .sort((a, b) => b[1] - a[1])[0]
  return top ? `${top[0]} (${top[1]})` : 'No dominant failure'
}

function scoreValue(row: ConfigComparisonMetrics): number | null {
  const values = [
    row.avg_faithfulness,
    row.avg_completeness,
    row.avg_retrieval_relevance,
    row.avg_context_coverage,
    row.avg_groundedness,
  ].filter((value): value is number => value != null)
  if (!values.length) return null
  return values.reduce((sum, value) => sum + value, 0) / values.length
}

function bestAndWorstRows(result: ConfigComparisonResponse): {
  best: ConfigComparisonMetrics | null
  worst: ConfigComparisonMetrics | null
} {
  const rows = result.configs ?? Object.values(result.buckets ?? {}).flat()
  const scored = rows
    .map((row) => ({ row, score: scoreValue(row) }))
    .filter((item): item is { row: ConfigComparisonMetrics; score: number } => item.score != null)
    .sort((a, b) => b.score - a.score)
  return { best: scored[0]?.row ?? null, worst: scored.at(-1)?.row ?? null }
}

function comparisonExplanation({
  best,
  worst,
  delta,
}: {
  best: ConfigComparisonMetrics | null
  worst: ConfigComparisonMetrics | null
  delta: number | null
}): string {
  if (!best || !worst || delta == null) {
    return 'Select configs and run comparison to see score movement, failure movement, and reliability notes.'
  }
  if (best.pipeline_config_id === worst.pipeline_config_id) {
    return 'Only one scored config is available, so this is a baseline snapshot rather than a head-to-head result.'
  }
  const movement = `${topFailureString(worst)} -> ${topFailureString(best)}`
  if (delta > 0.02) {
    return `Config #${best.pipeline_config_id} is ahead by ${(delta * 100).toFixed(1)} points. Failure movement: ${movement}.`
  }
  return `No clear winner yet. Score movement is ${(delta * 100).toFixed(1)} points, so treat this as directional until more shared queries are traced.`
}

function MetricsTable({ rows, title }: { rows: ConfigComparisonMetrics[]; title: string }) {
  if (!rows.length) {
    return (
      <div className="cl-card cl-empty">
        <EmptyState title={`No traced runs for ${title}`} detail="This bucket has no evaluation rows yet." />
      </div>
    )
  }
  return (
    <div className="cl-card">
      <h2>{title}</h2>
      <DataTable>
        <thead>
          <tr>
            <th>Config</th>
            <th>Traced</th>
            <th>Avg total ms</th>
            <th>Avg rel.</th>
            <th>Avg faith.</th>
            <th>Avg comp.</th>
            <th>Top failure</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((m) => (
            <tr key={m.pipeline_config_id}>
              <td>#{m.pipeline_config_id}</td>
              <td>{m.traced_runs}</td>
              <td>{m.avg_total_latency_ms?.toFixed?.(1) ?? '-'}</td>
              <td>{m.avg_retrieval_relevance?.toFixed?.(3) ?? '-'}</td>
              <td>{m.avg_faithfulness != null ? m.avg_faithfulness.toFixed(3) : '-'}</td>
              <td>{m.avg_completeness != null ? m.avg_completeness.toFixed(3) : '-'}</td>
              <td>
                <FailureBadge failureType={topFailureString(m).split(' ')[0]} />{' '}
                <span className="cl-muted">{topFailureString(m).match(/\(.+\)/)?.[0] ?? ''}</span>
              </td>
            </tr>
          ))}
        </tbody>
      </DataTable>
    </div>
  )
}

export function ComparisonView({
  pipelineConfigs,
  registryLoading,
  compareEvaluator,
  compareSelected,
  compareLoading,
  compareResult,
  onEvaluatorChange,
  onToggleCompare,
  onCompare,
  onReloadRegistry,
}: {
  pipelineConfigs: PipelineConfig[]
  registryLoading: boolean
  compareEvaluator: 'heuristic' | 'llm' | 'both'
  compareSelected: Set<number>
  compareLoading: boolean
  compareResult: ConfigComparisonResponse | null
  onEvaluatorChange: (value: 'heuristic' | 'llm' | 'both') => void
  onToggleCompare: (id: number) => void
  onCompare: () => void
  onReloadRegistry: () => void
}) {
  const { best, worst } = compareResult ? bestAndWorstRows(compareResult) : { best: null, worst: null }
  const bestScore = best ? scoreValue(best) : null
  const worstScore = worst ? scoreValue(worst) : null
  const delta = bestScore != null && worstScore != null ? bestScore - worstScore : null
  const verdict = delta == null ? 'Awaiting comparison' : delta > 0.02 ? 'Winner found' : 'Tie / directional'

  return (
    <section className="cl-compare-view">
      <div className="cl-card">
        <SectionHeader
          eyebrow="Diagnosis flow"
          title="Compare Pipeline Configs"
          description={
            <>
              Compare baseline vs changed retriever/prompt/config runs. Heuristic and LLM buckets remain separate
              to avoid mixing evaluator semantics.
            </>
          }
          actions={
            <button
              type="button"
              className="cl-btn cl-btn-secondary cl-btn-sm"
              disabled={registryLoading}
              onClick={onReloadRegistry}
            >
              Reload configs
            </button>
          }
        />

        {registryLoading ? <p className="cl-loading">Loading pipeline configs...</p> : null}

        {!pipelineConfigs.length && !registryLoading ? (
          <EmptyState title="No pipeline configs loaded" detail="Reload registry or create configs from Run benchmark." />
        ) : null}

        <div className="cl-compare-controls">
          <div className="cl-field">
            <label htmlFor="cev">Evaluator slice</label>
            <select
              id="cev"
              value={compareEvaluator}
              onChange={(ev) => onEvaluatorChange(ev.target.value as 'heuristic' | 'llm' | 'both')}
            >
              <option value="both">Both (separate tables: heuristic + LLM)</option>
              <option value="heuristic">Heuristic only</option>
              <option value="llm">LLM only</option>
            </select>
          </div>
          <div className="cl-actions cl-compare-actions">
            <button
              type="button"
              className="cl-btn"
              disabled={compareLoading || !compareSelected.size}
              onClick={onCompare}
            >
              {compareLoading ? 'Loading...' : 'Compare selected'}
            </button>
          </div>
        </div>

        <h3 className="cl-h3-muted">Pipeline configs</h3>
        <div className="cl-config-pick-grid">
          {pipelineConfigs.map((p) => (
            <label key={p.id} className="cl-config-pick" htmlFor={`cmp-${p.id}`}>
              <input
                type="checkbox"
                id={`cmp-${p.id}`}
                checked={compareSelected.has(p.id)}
                onChange={() => onToggleCompare(p.id)}
              />
              <span>
                <strong>{p.name}</strong>
                <small>
                  #{p.id} · top_k {p.top_k} · {p.chunk_strategy}
                </small>
              </span>
            </label>
          ))}
        </div>
      </div>

      <section className="cl-compare-demo-panel" aria-label="Baseline versus changed configuration">
        <div>
          <p className="cl-eyebrow">Baseline vs changed config</p>
          <h2>{verdict}</h2>
          <p>{comparisonExplanation({ best, worst, delta })}</p>
        </div>
        <div className="cl-compare-before-after">
          <div>
            <span>Baseline / weakest</span>
            <strong>{worst ? `#${worst.pipeline_config_id}` : '-'}</strong>
            <small>{worst ? topFailureString(worst) : 'Run comparison first'}</small>
          </div>
          <div>
            <span>Changed / strongest</span>
            <strong>{best ? `#${best.pipeline_config_id}` : '-'}</strong>
            <small>{best ? topFailureString(best) : 'Awaiting result'}</small>
          </div>
        </div>
      </section>

      <section className="cl-compare-outcome" aria-label="Comparison outcome">
        <MetricCard label="Outcome" value={verdict} detail={compareResult ? `Confidence: ${compareResult.comparison_confidence ?? 'LOW'}` : 'Run Compare to load'} tone={delta == null ? 'neutral' : delta > 0.02 ? 'good' : 'warn'} />
        <MetricCard label="Best config" value={best ? `#${best.pipeline_config_id}` : '-'} detail={bestScore != null ? `avg score ${(bestScore * 100).toFixed(1)}%` : 'no score yet'} tone="good" />
        <MetricCard label="Worst config" value={worst ? `#${worst.pipeline_config_id}` : '-'} detail={worstScore != null ? `avg score ${(worstScore * 100).toFixed(1)}%` : 'no score yet'} tone="bad" />
        <MetricCard label="Score movement" value={delta != null ? `${(delta * 100).toFixed(1)} pts` : '-'} detail={best && worst ? `${topFailureString(worst)} -> ${topFailureString(best)}` : 'failure movement unavailable'} tone="info" />
      </section>

      {compareResult?.buckets ? (
        <div className="cl-compare-grid">
          <div className="cl-compare-column">
            <MetricsTable rows={compareResult.buckets.heuristic ?? []} title="Heuristic bucket" />
            {compareResult.score_comparison_buckets?.heuristic ? (
              <div className="cl-card">
                <h3 className="cl-h3-muted">Heuristic — best vs worst (avg scores)</h3>
                <ScoreComparisonDl
                  summary={compareResult.score_comparison_buckets.heuristic}
                  metricsRows={compareResult.buckets.heuristic ?? []}
                />
              </div>
            ) : null}
          </div>
          <div className="cl-compare-column">
            <MetricsTable rows={compareResult.buckets.llm ?? []} title="LLM bucket" />
            {compareResult.score_comparison_buckets?.llm ? (
              <div className="cl-card">
                <h3 className="cl-h3-muted">LLM — best vs worst (avg scores)</h3>
                <ScoreComparisonDl summary={compareResult.score_comparison_buckets.llm} />
              </div>
            ) : null}
          </div>
        </div>
      ) : compareResult?.configs ? (
        <div className="cl-compare-column">
          <MetricsTable rows={compareResult.configs} title="Selected evaluator bucket" />
          {compareResult.score_comparison ? (
            <div className="cl-card">
              <h3 className="cl-h3-muted">Best vs worst (avg scores)</h3>
              <ScoreComparisonDl summary={compareResult.score_comparison} metricsRows={compareResult.configs} />
            </div>
          ) : null}
        </div>
      ) : (
        <div className="cl-card cl-empty">
          <EmptyState title="No comparison loaded" detail="Select one or more configs and run Compare." />
        </div>
      )}
    </section>
  )
}
