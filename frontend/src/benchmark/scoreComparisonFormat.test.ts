import { describe, expect, it } from 'vitest'
import { formatScoreDeltaPct } from './scoreComparisonFormat'

describe('formatScoreDeltaPct', () => {
  it('returns N/A for nullish or NaN', () => {
    expect(formatScoreDeltaPct(null)).toBe('N/A')
    expect(formatScoreDeltaPct(undefined)).toBe('N/A')
    expect(formatScoreDeltaPct(Number.NaN)).toBe('N/A')
  })

  it('formats finite numbers to one decimal and percent suffix', () => {
    expect(formatScoreDeltaPct(25.5)).toBe('25.5%')
    expect(formatScoreDeltaPct(0)).toBe('0.0%')
  })
})
