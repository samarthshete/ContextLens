import { describe, expect, it } from 'vitest'
import { isBenchmarkFormReady } from './formValidation'

describe('isBenchmarkFormReady', () => {
  it('returns false when any required field empty', () => {
    expect(isBenchmarkFormReady('', 1, 1)).toBe(false)
    expect(isBenchmarkFormReady(1, '', 1)).toBe(false)
    expect(isBenchmarkFormReady(1, 1, '')).toBe(false)
  })

  it('returns true when dataset, query case, and pipeline config set', () => {
    expect(isBenchmarkFormReady(1, 2, 3)).toBe(true)
  })
})
