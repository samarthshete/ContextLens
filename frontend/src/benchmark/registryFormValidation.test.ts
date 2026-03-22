import { describe, expect, it } from 'vitest'
import { validatePipelineChunkParams, validateTopK } from './registryFormValidation'

describe('validatePipelineChunkParams', () => {
  it('accepts overlap zero', () => {
    expect(validatePipelineChunkParams(512, 0)).toEqual({ ok: true })
  })
  it('accepts overlap less than size', () => {
    expect(validatePipelineChunkParams(100, 50)).toEqual({ ok: true })
  })
  it('rejects overlap equal to size', () => {
    const r = validatePipelineChunkParams(100, 100)
    expect(r.ok).toBe(false)
    if (!r.ok) expect(r.message).toMatch(/less than chunk size/i)
  })
  it('rejects overlap greater than size', () => {
    expect(validatePipelineChunkParams(100, 101).ok).toBe(false)
  })
})

describe('validateTopK', () => {
  it('accepts positive integers', () => {
    expect(validateTopK(5)).toEqual({ ok: true })
  })
  it('rejects zero', () => {
    expect(validateTopK(0).ok).toBe(false)
  })
})
