// @vitest-environment jsdom
import { describe, it, expect } from 'vitest'
import { buildTimelineModel, fmtMs } from './runTimeline'

describe('fmtMs', () => {
  it('formats sub-second values as ms', () => {
    expect(fmtMs(120)).toBe('120ms')
    expect(fmtMs(0)).toBe('0ms')
  })

  it('formats >= 1000 as seconds', () => {
    expect(fmtMs(3100)).toBe('3.1s')
    expect(fmtMs(1000)).toBe('1.0s')
  })
})

describe('buildTimelineModel', () => {
  it('full run: all phases present', () => {
    const m = buildTimelineModel(120, 3100, 900, 4120)
    expect(m.hasData).toBe(true)
    expect(m.phases).toHaveLength(4) // retrieval, generation, evaluation, total

    const gen = m.phases.find((p) => p.key === 'generation')!
    expect(gen.dominant).toBe(true)
    expect(gen.durationMs).toBe(3100)
    expect(gen.pct).toBeCloseTo(75.2, 0)

    const ret = m.phases.find((p) => p.key === 'retrieval')!
    expect(ret.dominant).toBe(false)
    expect(ret.pct).toBeCloseTo(2.9, 0)

    const total = m.phases.find((p) => p.key === 'total')!
    expect(total.durationMs).toBe(4120)
    expect(total.pct).toBeNull() // total has no % of itself

    expect(m.summary).toContain('Generation dominated')
  })

  it('heuristic run: retrieval + evaluation only', () => {
    const m = buildTimelineModel(10, null, 5, 15)
    expect(m.hasData).toBe(true)

    const gen = m.phases.find((p) => p.key === 'generation')!
    expect(gen.durationMs).toBeNull()
    expect(gen.pct).toBeNull()
    expect(gen.dominant).toBe(false)

    const ret = m.phases.find((p) => p.key === 'retrieval')!
    expect(ret.dominant).toBe(true)
    expect(ret.pct).toBeCloseTo(66.7, 0)

    expect(m.summary).toContain('Retrieval dominated')
  })

  it('single phase only (retrieval)', () => {
    const m = buildTimelineModel(200, null, null, 200)
    expect(m.hasData).toBe(true)

    const ret = m.phases.find((p) => p.key === 'retrieval')!
    expect(ret.dominant).toBe(false) // only 1 measured phase — no dominance
    expect(m.summary).toContain('Retrieval was the only measured phase')
  })

  it('single phase with overhead in total', () => {
    const m = buildTimelineModel(200, null, null, 350)
    expect(m.summary).toContain('unmeasured overhead')
  })

  it('total missing', () => {
    const m = buildTimelineModel(100, 300, 50, null)
    expect(m.hasData).toBe(true)
    // No percentages when total is null
    m.phases.forEach((p) => expect(p.pct).toBeNull())
    expect(m.summary).toContain('Total latency not available')
  })

  it('component sum exceeds total — no percentages', () => {
    // This can happen due to measurement granularity
    const m = buildTimelineModel(100, 300, 50, 400)
    // Sum = 450 > 400
    const ret = m.phases.find((p) => p.key === 'retrieval')!
    expect(ret.pct).toBeNull()
    expect(m.summary).toContain('percentages omitted')
  })

  it('no data at all', () => {
    const m = buildTimelineModel(null, null, null, null)
    expect(m.hasData).toBe(false)
    expect(m.summary).toBe('No timing data available.')
  })

  it('total only — no per-phase breakdown', () => {
    const m = buildTimelineModel(null, null, null, 500)
    expect(m.hasData).toBe(true)
    expect(m.summary).toContain('no per-phase breakdown')
  })

  it('zero durations are valid', () => {
    const m = buildTimelineModel(0, 0, 0, 0)
    expect(m.hasData).toBe(true)
    // total=0 means no percentages (division by zero guard)
    m.phases.filter((p) => p.key !== 'total').forEach((p) => expect(p.pct).toBeNull())
  })
})
