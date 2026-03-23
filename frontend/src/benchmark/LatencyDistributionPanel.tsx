import type { LatencyDistribution, LatencyDistributionSection } from '../api/types'
import { barWidthPct, formatDistRow, latencyPhaseScaleMs } from './dashboardAnalyticsFormat'
import {
  DASHBOARD_LATENCY_DIST_MIN_RUNS,
  DASHBOARD_LATENCY_HIGH_VARIANCE_RATIO,
  DASHBOARD_LATENCY_LOW_SAMPLE_THRESHOLD,
} from './dashboardConstants'

const PHASES = ['retrieval', 'generation', 'evaluation', 'total'] as const

const PHASE_LABELS: Record<(typeof PHASES)[number], string> = {
  retrieval: 'Retrieval',
  generation: 'Generation',
  evaluation: 'Evaluation',
  total: 'Total',
}

const MEDIAN_VS_AVG_COPY =
  'Median is more representative than average when cold-start outliers are present.'

const LATENCY_SKEW_WARNING =
  'Latency is highly skewed due to local execution and cold-start effects. Median (P50) is more representative than average. These values are directional and not SLA-grade measurements.'

/** True when P95 / P50 ratio exceeds the configured threshold (both non-null, P50 > 0). */
function isHighVariance(dist: LatencyDistribution): boolean {
  if (dist.p95_ms == null || dist.median_ms == null || dist.median_ms <= 0) return false
  return dist.p95_ms / dist.median_ms > DASHBOARD_LATENCY_HIGH_VARIANCE_RATIO
}

/** True when phase has data but fewer than the low-sample threshold. */
function isLowSampleForStats(dist: LatencyDistribution): boolean {
  return dist.count > 0 && dist.count < DASHBOARD_LATENCY_LOW_SAMPLE_THRESHOLD
}

function LatencyCompareBars({ dist }: { dist: LatencyDistribution }) {
  const scale = latencyPhaseScaleMs(dist)
  const hasMetrics = [dist.median_ms, dist.p95_ms, dist.max_ms].some(
    (v) => v != null && Number.isFinite(v),
  )
  const rows: { label: string; ms: number | null; cls: string }[] = [
    { label: 'Median (P50)', ms: dist.median_ms, cls: 'cl-latency-hbar-fill--median' },
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
  const lowSample = dist.count > 0 && dist.count < DASHBOARD_LATENCY_DIST_MIN_RUNS
  const sufficient = dist.count >= DASHBOARD_LATENCY_DIST_MIN_RUNS

  const highVar = isHighVariance(dist)
  const lowSampleStats = isLowSampleForStats(dist)

  return (
    <div className="cl-card cl-latency-phase-block">
      <h3 className="cl-latency-phase-title">{PHASE_LABELS[phase]}</h3>
      {dist.count === 0 ? (
        <p className="cl-muted" data-testid={`latency-phase-empty-${phase}`}>
          No samples for this phase.
        </p>
      ) : lowSample ? (
        <p className="cl-muted" data-testid={`latency-phase-insufficient-${phase}`}>
          Insufficient samples for distribution ({dist.count} run{dist.count === 1 ? '' : 's'})
        </p>
      ) : sufficient ? (
        <LatencyCompareBars dist={dist} />
      ) : null}
      {dist.count > 0 ? (
        <div className="cl-latency-phase-badges" data-testid={`latency-phase-badges-${phase}`}>
          {highVar ? (
            <span className="cl-badge cl-badge--warn" data-testid={`latency-high-variance-${phase}`}>
              High variance (skewed distribution)
            </span>
          ) : null}
          {lowSampleStats ? (
            <span className="cl-badge cl-badge--info" data-testid={`latency-low-sample-${phase}`}>
              Low sample ({dist.count}) — not reliable
            </span>
          ) : null}
        </div>
      ) : null}
      {sufficient ? (
        <dl className="cl-latency-phase-dl" data-testid={`latency-phase-dl-${phase}`}>
          <div className="cl-latency-phase-row">
            <dt>Count</dt>
            <dd>{row.count}</dd>
          </div>
          <div className="cl-latency-phase-row cl-latency-phase-row--primary">
            <dt>Median (P50)</dt>
            <dd>{row.median}</dd>
          </div>
          <div className="cl-latency-phase-row cl-latency-phase-row--primary">
            <dt>P95</dt>
            <dd>{row.p95}</dd>
          </div>
          <div className="cl-latency-phase-row">
            <dt>Min</dt>
            <dd>{row.min}</dd>
          </div>
          <div className="cl-latency-phase-row">
            <dt>Max</dt>
            <dd>{row.max}</dd>
          </div>
          <div className="cl-latency-phase-row cl-latency-phase-row--avg-secondary">
            <dt>Mean</dt>
            <dd>{row.avg}</dd>
          </div>
        </dl>
      ) : null}
    </div>
  )
}

export function LatencyDistributionPanel({ data }: { data: LatencyDistributionSection }) {
  const hasAny = PHASES.some((p) => data[p].count > 0)

  return (
    <section className="cl-card" aria-label="Latency distribution" data-testid="latency-distribution">
      <h2>Latency Distribution</h2>
      <p className="cl-muted">
        From <code>analytics.latency_distribution</code> — non-null samples per phase. Latency in local
        experiments is <strong>directional</strong>: cold-start and cache-warm effects can skew averages and
        tails; do not read low numbers as a benchmark guarantee.
      </p>
      {!hasAny ? (
        <p className="cl-muted cl-empty-inline">No latency data available yet.</p>
      ) : (
        <>
          <p className="cl-msg cl-msg-warn cl-latency-skew-warning" data-testid="latency-skew-warning" role="alert">
            {LATENCY_SKEW_WARNING}
          </p>
          <p className="cl-muted cl-latency-median-note" data-testid="latency-median-vs-avg-note">
            {MEDIAN_VS_AVG_COPY}
          </p>
          <div className="cl-latency-dist-grid">
            {PHASES.map((phase) => (
              <LatencyPhaseBlock key={phase} phase={phase} dist={data[phase]} />
            ))}
          </div>
        </>
      )}
    </section>
  )
}
