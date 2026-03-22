/** @vitest-environment jsdom */
import '@testing-library/jest-dom/vitest'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { DocumentDetailPanel } from './DocumentDetailPanel'

vi.mock('../api/client', () => ({
  api: {
    getDocument: vi.fn(),
    getDocumentChunks: vi.fn(),
  },
  ApiError: class ApiError extends Error {
    status: number
    constructor(status: number, detail: string) {
      super(detail)
      this.status = status
      this.name = 'ApiError'
    }
  },
}))

import { api, ApiError } from '../api/client'

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/documents/:documentId" element={<DocumentDetailPanel />} />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
})

afterEach(() => {
  cleanup()
})

describe('DocumentDetailPanel', () => {
  it('shows invalid id message for non-numeric param', async () => {
    renderAt('/documents/abc')
    await waitFor(() => {
      expect(screen.getByTestId('document-detail-invalid')).toBeInTheDocument()
    })
    expect(api.getDocument).not.toHaveBeenCalled()
  })

  it('loads metadata and chunks', async () => {
    vi.mocked(api.getDocument).mockResolvedValue({
      id: 5,
      title: 'Corpus A',
      source_type: 'txt',
      status: 'processed',
      created_at: '2026-01-01T00:00:00.000Z',
      metadata_json: { chunk_size: 256 },
    })
    vi.mocked(api.getDocumentChunks).mockResolvedValue([
      {
        id: 101,
        document_id: 5,
        content: 'hello chunk',
        chunk_index: 0,
        start_char: 0,
        end_char: 5,
        metadata_json: null,
      },
    ])

    renderAt('/documents/5')

    await waitFor(() => {
      expect(screen.getByTestId('document-detail-meta')).toHaveTextContent('Corpus A')
    })
    expect(screen.getByTestId('document-detail-chunks')).toHaveTextContent('Chunks (1)')
    expect(screen.getByTestId('document-chunk-0')).toHaveTextContent('hello chunk')
  })

  it('shows not found on 404', async () => {
    vi.mocked(api.getDocument).mockRejectedValue(new ApiError(404, 'Document not found.'))
    vi.mocked(api.getDocumentChunks).mockRejectedValue(new ApiError(404, 'Document not found.'))

    renderAt('/documents/99')

    await waitFor(() => {
      expect(screen.getByText(/Document not found/i)).toBeInTheDocument()
    })
  })
})
