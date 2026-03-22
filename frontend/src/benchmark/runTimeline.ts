/**
 * runTimeline.ts — pure helpers for run-phase timeline.
 *
 * Consumes the four latency fields from RunDetail and produces a
 * render-ready model: per-phase rows with durations, percentages
 * (only when valid), dominant-phase identification, and a short
 * plain-English summary.
 */

export interface PhaseRow {
  /** Display label. */
  label: string
  /** Machine key for styling / test selectors. */
  key: 'retrieval' | 'generation' | 'evaluation' | 'total'
  /** Duration in ms, or null when not measured. */
  durationMs: number | null
  /** Percentage of total (0–100), or null when not computable. */
  pct: number | null
  /** True when this phase had the highest duration among component phases. */
  dominant: boolean
}

export interface TimelineModel {
  phases: PhaseRow[]
  /** Short plain-English summary of where time went. */
  summary: string
  /** True when at least one component phase has a valid duration. */
  hasData: boolean
}

/** Phase definitions in display order (component phases only — total is separate). */
const COMPONENT_PHASES = [
  { label: 'Retrieval', key: 'retrieval' as const },
  { label: 'Generation', key: 'generation' as const },
  { label: 'Evaluation', key: 'evaluation' as const },
] as const

/**
 * Build a timeline model from the four latency fields on a run detail.
 * All inputs are nullable — the model handles every combination safely.
 */
export function buildTimelineModel(
  retrievalMs: number | null,
  generationMs: number | null,
  evaluationMs: number | null,
  totalMs: number | null,
): TimelineModel {
  const durations: Record<string, number | null> = {
    retrieval: retrievalMs,
    generation: generationMs,
    evaluation: evaluationMs,
  }

  // Identify measured component phases and find dominant.
  const measured = COMPONENT_PHASES.filter((p) => durations[p.key] != null && durations[p.key]! >= 0)
  const maxDuration = measured.length > 0 ? Math.max(...measured.map((p) => durations[p.key]!)) : null

  // Percentages are valid only when total > 0 and component sum ≤ total.
  const componentSum = measured.reduce((s, p) => s + durations[p.key]!, 0)
  const canComputePct = totalMs != null && totalMs > 0 && measured.length > 0 && componentSum <= totalMs

  const componentPhases: PhaseRow[] = COMPONENT_PHASES.map((p) => {
    const d = durations[p.key]
    return {
      label: p.label,
      key: p.key,
      durationMs: d,
      pct: canComputePct && d != null ? roundPct(d, totalMs!) : null,
      dominant: d != null && maxDuration != null && d === maxDuration && measured.length > 1,
    }
  })

  const totalRow: PhaseRow = {
    label: 'Total',
    key: 'total',
    durationMs: totalMs,
    pct: null, // total is the reference — no percentage of itself
    dominant: false,
  }

  const phases = [...componentPhases, totalRow]
  const summary = buildSummary(measured, durations, totalMs, canComputePct, maxDuration)

  return {
    phases,
    summary,
    hasData: measured.length > 0 || totalMs != null,
  }
}

/** Round to one decimal, clamped 0–100. */
function roundPct(part: number, whole: number): number {
  const raw = (part / whole) * 100
  return Math.round(raw * 10) / 10
}

function buildSummary(
  measured: readonly { label: string; key: string }[],
  durations: Record<string, number | null>,
  totalMs: number | null,
  canComputePct: boolean,
  maxDuration: number | null,
): string {
  if (measured.length === 0 && totalMs == null) {
    return 'No timing data available.'
  }

  if (measured.length === 0 && totalMs != null) {
    return `Total latency: ${fmtMs(totalMs)}, but no per-phase breakdown available.`
  }

  if (measured.length === 1) {
    const p = measured[0]
    const suffix = totalMs != null && totalMs > durations[p.key]!
      ? ` (total ${fmtMs(totalMs)} includes unmeasured overhead)`
      : ''
    return `${p.label} was the only measured phase: ${fmtMs(durations[p.key]!)}${suffix}.`
  }

  // Multiple measured phases.
  if (maxDuration != null && canComputePct) {
    const dominant = measured.find((p) => durations[p.key] === maxDuration)!
    const pct = roundPct(maxDuration, totalMs!)
    return `${dominant.label} dominated at ${fmtMs(maxDuration)} (${pct}% of ${fmtMs(totalMs!)}).`
  }

  if (maxDuration != null) {
    const dominant = measured.find((p) => durations[p.key] === maxDuration)!
    const suffix = totalMs == null
      ? ' Total latency not available.'
      : ' Component sum exceeds total — percentages omitted.'
    return `${dominant.label} was slowest at ${fmtMs(maxDuration)}.${suffix}`
  }

  return 'Phase timing data is partial.'
}

/** Format milliseconds for display. */
export function fmtMs(ms: number): string {
  if (ms >= 1000) {
    const s = ms / 1000
    return `${s.toFixed(1)}s`
  }
  return `${Math.round(ms)}ms`
}
