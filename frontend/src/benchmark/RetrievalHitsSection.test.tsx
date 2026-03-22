/** @vitest-environment jsdom */
import '@testing-library/jest-dom/vitest'
import { cleanup, render, screen } from '@testing-library/react'
import type { ComponentProps } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it } from 'vitest'
import type { RunDetail } from '../api/types'
import { RetrievalHitsSection } from './RetrievalHitsSection'

const hit = (
  rank: number,
  documentId: number,
  content: string,
): RunDetail['retrieval_hits'][number] => ({
  rank,
  score: 0.5 + rank * 0.01,
  chunk_id: 100 + rank,
  document_id: documentId,
  content,
  chunk_index: rank - 1,
})

function renderHits(props: ComponentProps<typeof RetrievalHitsSection>) {
  return render(
    <MemoryRouter>
      <RetrievalHitsSection {...props} />
    </MemoryRouter>,
  )
}

describe('RetrievalHitsSection', () => {
  afterEach(() => {
    cleanup()
  })

  it('shows id-only source when title map is empty', () => {
    renderHits({
      hits: [hit(1, 42, 'body')],
      documentTitleById: new Map(),
    })
    expect(screen.getByTestId('retrieval-hit-1')).toHaveTextContent('Document #42')
    expect(screen.getByTestId('retrieval-hit-1')).toHaveTextContent('score 0.5100')
    const link = screen.getByTestId('retrieval-hit-source-link-1')
    expect(link).toHaveAttribute('href', '/documents/42')
  })

  it('shows resolved title when map has document', () => {
    const m = new Map([[7, 'My PDF']])
    renderHits({
      hits: [hit(1, 7, 'x'), hit(2, 7, 'y')],
      documentTitleById: m,
    })
    expect(screen.getByTestId('retrieval-hit-1')).toHaveTextContent('My PDF · document #7')
    expect(screen.getByRole('status')).toHaveTextContent(/same source/i)
    expect(screen.getByTestId('retrieval-hit-source-link-1')).toHaveAttribute('href', '/documents/7')
  })

  it('shows plain source when document_id is missing', () => {
    const hits = [
      {
        rank: 1,
        score: 0.51,
        chunk_id: 99,
        document_id: null,
        content: 'c',
        chunk_index: 0,
      },
    ] as unknown as RunDetail['retrieval_hits']
    renderHits({ hits, documentTitleById: new Map() })
    expect(screen.getByTestId('retrieval-hit-source-plain-1')).toHaveTextContent('—')
    expect(screen.queryByTestId('retrieval-hit-source-link-1')).toBeNull()
  })

  it('shows empty state', () => {
    renderHits({ hits: [], documentTitleById: new Map() })
    expect(screen.getByText(/No chunks retrieved/i)).toBeInTheDocument()
  })
})
