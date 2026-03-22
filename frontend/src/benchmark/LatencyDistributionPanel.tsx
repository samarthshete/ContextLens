import type { LatencyDistribution, LatencyDistributionSection } from '../api/types'
import { barWidthPct, formatDistRow, latencyPhaseScaleMs } from './dashboardAnalyticsFormat'

const PHASES = ['retrieval', 'generation', 'evaluation', 'total'] as const

const PHASE_LABELS: Record<(typeof PHASES)[number], string> = {
  retrieval: 'Retrieval',
  generation: 'Generation',
  evaluation: 'Evaluation',
  total: 'Total',
}

function LatencyCompareBars({ dist }: { dist: LatencyDistribution }) {
  const scale = latencyPhaseScaleMs(dist)
  const hasMetrics = [dist.median_ms, dist.p95_ms, dist.max_ms].some(
    (v) => v != null && Number.isFinite(v),
  )
  const rows: { label: string; ms: number | null; cls: string }[] = [
    { label: 'Median', ms: dist.median_ms, cls: 'cl-latency-hbar-fill--median' },
    { label: 'P95', ms: dist.p95_ms, cls: 'cl-latency-hbar-fill--p95' },
    { label: 'Max', ms: dist.max_ms, cls: 'cl-latency-hbar-fill--max' },
  ]
  return (
    <div className="cl-latency-hbar-block" aria-label="Latency comparison within phase">
      <p className="cl-latency-hbar-caption">
        Scale = max(median, p95, max) for this phase (
        {hasMetrics ? `${Math.round(scale)} ms` : 'no samples'}).
      </p>
      {rows.map(({ label, ms, cls }) => (
        <div key={label} className="cl-latency-hbar-row">
          <span className="cl-latency-hbar-label">{label}</span>
          <div className="cl-latency-hbar-track">
            <div
              className={`cl-latency-hbar-fill ${cls}`}
              style={{ width: `${barWidthPct(ms, scale)}%` }}
            />
          </div>
          <span className="cl-latency-hbar-value">
            {ms != null ? `${Math.round(ms)} ms` : 'N/A'}
          </span>
        </div>
      ))}
    </div>
  )
}

function LatencyPhaseBlock({
  phase,
  dist,
}: {
  phase: (typeof PHASES)[number]
  dist: LatencyDistribution
}) {
  const row = formatDistRow(dist)
  return (
    <div className="cl-card cl-latency-phase-block">
      <h3 className="cl-latency-phase-title">{PHASE_LABELS[phase]}</h3>
      {dist.count > 0 ? <LatencyCompareBars dist={dist} /> : null}
      <dl className="cl-latency-phase-dl">
        <div className="cl-latency-phase-row">
          <dt>Count</dt>
          <dd>{row.count}</dd>
        </div>
        <div className="cl-latency-phase-row">
          <dt>Min</dt>
          <dd>{row.min}</dd>
        </div>
        <div className="cl-latency-phase-row">
          <dt>Max</dt>
          <dd>{row.max}</dd>
        </div>
        <div className="cl-latency-phase-row">
          <dt>Avg</dt>
          <dd>{row.avg}</dd>
        </div>
        <div className="cl-latency-phase-row">
          <dt>Median</dt>
          <dd>{row.median}</dd>
        </div>
        <div className="cl-latency-phase-row">
          <dt>P95</dt>
          <dd>{row.p95}</dd>
        </div>
      </dl>
    </div>
  )
}

export function LatencyDistributionPanel({ data }: { data: LatencyDistributionSection }) {
  const hasAny = PHASES.some((p) => data[p].count > 0)

  return (
    <section className="cl-card" aria-label="Latency distribution" data-testid="latency-distribution">
      <h2>Latency Distribution</h2>
      <p className="cl-muted">
        From <code>analytics.latency_distribution</code> — min / max / avg / median / p95 over non-null
        samples per phase.
      </p>
      {!hasAny ? (
        <p className="cl-muted cl-empty-inline">No latency data available yet.</p>
      ) : null}
      <div className="cl-latency-dist-grid">
        {PHASES.map((phase) => (
          <LatencyPhaseBlock key={phase} phase={phase} dist={data[phase]} />
        ))}
      </div>
    </section>
  )
}
