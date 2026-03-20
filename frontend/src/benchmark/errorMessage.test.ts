import { describe, expect, it } from 'vitest'
import { ApiError } from '../api/client'
import { describeApiError, describeDocumentUploadError } from './errorMessage'

describe('describeApiError', () => {
  it('maps 503 to LLM not configured', () => {
    expect(describeApiError(new ApiError(503, 'claude_api_key missing'))).toBe('LLM not configured')
  })

  it('maps 404 to Invalid selection', () => {
    expect(describeApiError(new ApiError(404, 'Document not found.'))).toBe('Invalid selection')
  })

  it('maps 502 to LLM request failed', () => {
    expect(describeApiError(new ApiError(502, 'Anthropic API error: x'))).toBe('LLM request failed')
  })

  it('maps 422 to Invalid input', () => {
    expect(describeApiError(new ApiError(422, 'validation'))).toBe('Invalid input')
  })

  it('handles generic Error', () => {
    expect(describeApiError(new Error('network'))).toBe('network')
  })

  it('maps 413 to file too large', () => {
    expect(describeApiError(new ApiError(413, 'x'))).toBe('File too large.')
  })
})

describe('describeDocumentUploadError', () => {
  it('maps 413', () => {
    expect(describeDocumentUploadError(new ApiError(413, 'x'))).toBe('File too large.')
  })

  it('maps 422 with detail', () => {
    expect(describeDocumentUploadError(new ApiError(422, 'corrupt'))).toBe('corrupt')
  })

  it('maps 400 with detail', () => {
    expect(describeDocumentUploadError(new ApiError(400, "Unsupported file type '.'"))).toBe(
      "Unsupported file type '.'",
    )
  })

  it('falls back for unknown status', () => {
    expect(describeDocumentUploadError(new ApiError(500, 'oops'))).toBe('oops')
  })
})
