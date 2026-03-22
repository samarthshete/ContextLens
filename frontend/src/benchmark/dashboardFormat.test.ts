import { describe, expect, it } from 'vitest'
import { costAvailabilityLine, formatLatencyMs, formatLatencySec, formatUsd } from './dashboardFormat'

describe('formatLatencyMs', () => {
  it('formats number', () => {
    expect(formatLatencyMs(42)).toBe('42 ms')
  })
  it('returns N/A for null', () => {
    expect(formatLatencyMs(null)).toBe('N/A')
  })
})

describe('formatLatencySec', () => {
  it('formats seconds with three decimals', () => {
    expect(formatLatencySec(1.5)).toBe('1.500 s')
  })
  it('returns N/A for null', () => {
    expect(formatLatencySec(null)).toBe('N/A')
  })
})

describe('formatUsd', () => {
  it('returns N/A for null', () => {
    expect(formatUsd(null)).toBe('N/A')
  })
  it('shows explicit zero', () => {
    expect(formatUsd(0)).toBe('$0.00')
  })
  it('formats small amounts', () => {
    expect(formatUsd(0.000106)).toBe('$0.000106')
  })
})

describe('costAvailabilityLine', () => {
  it('describes no rows', () => {
    expect(costAvailabilityLine({ evaluation_rows_with_cost: 0, evaluation_rows_cost_not_available: 0 })).toBe(
      'No evaluation rows yet.',
    )
  })
  it('describes split', () => {
    expect(
      costAvailabilityLine({ evaluation_rows_with_cost: 2, evaluation_rows_cost_not_available: 1 }),
    ).toMatch(/2 row\(s\) with cost/)
  })
})
