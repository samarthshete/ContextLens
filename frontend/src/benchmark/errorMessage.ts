import { ApiError } from '../api/client'

/** User-facing text for common API failures when creating or loading runs. */
export function describeApiError(err: unknown): string {
  if (err instanceof ApiError) {
    switch (err.status) {
      case 404:
        return 'Invalid selection'
      case 413:
        return 'File too large.'
      case 400:
        return err.detail || 'Invalid request.'
      case 422:
        return 'Invalid input'
      case 502:
        return 'LLM request failed'
      case 503:
        return 'LLM not configured'
      default:
        return err.detail || `Request failed (${err.status}).`
    }
  }
  if (err instanceof Error) return err.message
  return String(err)
}

/** Messages for ``POST /documents`` (upload) failures. */
export function describeDocumentUploadError(err: unknown): string {
  if (err instanceof ApiError) {
    switch (err.status) {
      case 413:
        return 'File too large.'
      case 422:
        return err.detail || 'Invalid or unreadable file.'
      case 400:
        return err.detail || 'Invalid file type.'
      default:
        return err.detail || 'Upload failed.'
    }
  }
  if (err instanceof Error) return err.message
  return String(err)
}
