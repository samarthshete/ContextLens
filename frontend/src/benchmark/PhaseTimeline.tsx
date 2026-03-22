import type { RunDetail } from '../api/types'
import { buildTimelineModel, fmtMs } from './runTimeline'
import type { PhaseRow } from './runTimeline'

export interface PhaseTimelineProps {
  runDetail: RunDetail
}

/**
 * Compact phase-timeline bar for a single run.
 * Shows retrieval / generation / evaluation / total with relative bars
 * and a plain-English summary of where time was spent.
 */
export function PhaseTimeline({ runDetail }: PhaseTimelineProps) {
  const model = buildTimelineModel(
    runDetail.retrieval_latency_ms,
    runDetail.generation_latency_ms,
    runDetail.evaluation_latency_ms,
    runDetail.total_latency_ms,
  )

  if (!model.hasData) return null

  return (
    <section className="cl-subsection cl-phase-timeline" data-testid="phase-timeline">
      <h3>Phase timeline</h3>
      <p className="cl-muted cl-timeline-summary">{model.summary}</p>
      <div className="cl-timeline-rows">
        {model.phases.map((row) => (
          <TimelineRow key={row.key} row={row} />
        ))}
      </div>
    </section>
  )
}

function TimelineRow({ row }: { row: PhaseRow }) {
  const unavailable = row.durationMs == null

  return (
    <div
      className={`cl-timeline-row${row.dominant ? ' cl-timeline-dominant' : ''}${row.key === 'total' ? ' cl-timeline-total' : ''}`}
      data-testid={`timeline-${row.key}`}
    >
      <span className="cl-timeline-label">{row.label}</span>
      <span className="cl-timeline-bar-wrap">
        {!unavailable && row.pct != null ? (
          <span
            className="cl-timeline-bar"
            style={{ width: `${Math.max(row.pct, 1)}%` }}
            aria-label={`${row.pct}%`}
          />
        ) : null}
      </span>
      <span className="cl-timeline-value">
        {unavailable ? (
          <span className="cl-muted">—</span>
        ) : (
          <>
            {fmtMs(row.durationMs!)}
            {row.pct != null ? <span className="cl-timeline-pct"> ({row.pct}%)</span> : null}
          </>
        )}
      </span>
    </div>
  )
}
