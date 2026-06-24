import type { ReactNode } from 'react'

export type BadgeTone = 'neutral' | 'good' | 'warn' | 'bad' | 'info'

export function SectionHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow?: string
  title: string
  description?: ReactNode
  actions?: ReactNode
}) {
  return (
    <div className="cl-section-header">
      <div>
        {eyebrow ? <p className="cl-eyebrow">{eyebrow}</p> : null}
        <h2>{title}</h2>
        {description ? <p className="cl-section-description">{description}</p> : null}
      </div>
      {actions ? <div className="cl-section-actions">{actions}</div> : null}
    </div>
  )
}

export function MetricCard({
  label,
  value,
  detail,
  tone = 'neutral',
}: {
  label: string
  value: ReactNode
  detail?: ReactNode
  tone?: BadgeTone
}) {
  return (
    <div className={`cl-metric-card cl-dash-stat cl-metric-card--${tone}`}>
      <span className="cl-metric-label cl-dash-stat-label">{label}</span>
      <strong className="cl-metric-value cl-dash-stat-value">{value}</strong>
      {detail ? <span className="cl-metric-detail">{detail}</span> : null}
    </div>
  )
}

export function StatusBadge({ status }: { status: string }) {
  const normalized = status.replace(/_/g, '-')
  return (
    <span className={`cl-status-badge cl-status-badge--${normalized}`} title={status}>
      {status.replace(/_/g, ' ')}
    </span>
  )
}

export function ScoreBadge({ score, label = 'score' }: { score: number | null | undefined; label?: string }) {
  const pct = score == null ? null : Math.round(score * 100)
  const tone = pct == null ? 'neutral' : pct >= 80 ? 'good' : pct >= 60 ? 'warn' : 'bad'
  return (
    <span className={`cl-score-badge cl-score-badge--${tone}`}>
      <span>{label}</span>
      <strong>{pct == null ? 'N/A' : `${pct}%`}</strong>
    </span>
  )
}

export function FailureBadge({ failureType }: { failureType: string | null | undefined }) {
  const clean = failureType || 'NO_FAILURE'
  const tone = clean === 'NO_FAILURE' ? 'good' : clean.includes('RETRIEVAL') ? 'warn' : 'bad'
  return <span className={`cl-failure-badge cl-failure-badge--${tone}`}>{clean}</span>
}

export function EmptyState({ title, detail }: { title: string; detail?: ReactNode }) {
  return (
    <div className="cl-empty-state">
      <strong>{title}</strong>
      {detail ? <p>{detail}</p> : null}
    </div>
  )
}

export function ErrorState({ message }: { message: string }) {
  return (
    <div className="cl-error-state" role="alert">
      <strong>Unable to load this view</strong>
      <p>{message}</p>
    </div>
  )
}

export function TracePanel({
  title,
  meta,
  children,
}: {
  title: string
  meta?: ReactNode
  children: ReactNode
}) {
  return (
    <section className="cl-trace-panel">
      <div className="cl-trace-panel-header">
        <h3>{title}</h3>
        {meta ? <div className="cl-trace-panel-meta">{meta}</div> : null}
      </div>
      <div className="cl-trace-panel-body">{children}</div>
    </section>
  )
}

export function DataTable({
  children,
  className = '',
}: {
  children: ReactNode
  className?: string
}) {
  return (
    <div className={`cl-data-table-wrap ${className}`}>
      <table className="cl-table cl-data-table">{children}</table>
    </div>
  )
}
