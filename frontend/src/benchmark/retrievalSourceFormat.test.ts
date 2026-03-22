import { describe, expect, it } from 'vitest'
import type { DocumentListItem } from '../api/types'
import {
  analyzeRetrievalSourceDiversity,
  documentTitleLookupMap,
  formatRetrievalDocumentLabel,
  retrievalSourceDiversityNote,
} from './retrievalSourceFormat'

describe('retrievalSourceFormat', () => {
  describe('documentTitleLookupMap', () => {
    it('maps ids to titles', () => {
      const docs: DocumentListItem[] = [
        { id: 1, title: 'Alpha', source_type: 'pdf', status: 'processed', created_at: '' },
      ]
      const m = documentTitleLookupMap(docs)
      expect(m.get(1)).toBe('Alpha')
    })

    it('skips empty titles', () => {
      const docs: DocumentListItem[] = [
        { id: 2, title: '  ', source_type: 'txt', status: 'processed', created_at: '' },
      ]
      const m = documentTitleLookupMap(docs)
      expect(m.has(2)).toBe(false)
    })
  })

  describe('formatRetrievalDocumentLabel', () => {
    it('uses title when in map', () => {
      const m = new Map([[7, 'Q3 Notes']])
      expect(formatRetrievalDocumentLabel(7, m)).toBe('Q3 Notes · document #7')
    })

    it('falls back to id only when unknown', () => {
      expect(formatRetrievalDocumentLabel(99, new Map())).toBe('Document #99')
    })
  })

  describe('analyzeRetrievalSourceDiversity', () => {
    it('detects single-document dominance', () => {
      const d = analyzeRetrievalSourceDiversity([
        { document_id: 1 },
        { document_id: 1 },
        { document_id: 1 },
      ])
      expect(d.uniqueDocumentCount).toBe(1)
      expect(d.singleDocumentId).toBe(1)
      expect(d.hitCount).toBe(3)
    })

    it('detects multiple sources', () => {
      const d = analyzeRetrievalSourceDiversity([{ document_id: 1 }, { document_id: 2 }])
      expect(d.uniqueDocumentCount).toBe(2)
      expect(d.singleDocumentId).toBeNull()
    })
  })

  describe('retrievalSourceDiversityNote', () => {
    it('returns null for no hits', () => {
      expect(
        retrievalSourceDiversityNote(
          { hitCount: 0, uniqueDocumentCount: 0, singleDocumentId: null },
          new Map(),
        ),
      ).toBeNull()
    })

    it('warns when all hits share one document', () => {
      const div = analyzeRetrievalSourceDiversity([
        { document_id: 5 },
        { document_id: 5 },
      ])
      const note = retrievalSourceDiversityNote(div, new Map([[5, 'Only Doc']]))
      expect(note).toMatch(/same source/i)
      expect(note).toMatch(/Only Doc/)
      expect(note).toMatch(/2/)
    })

    it('notes distinct document count when mixed', () => {
      const div = analyzeRetrievalSourceDiversity([{ document_id: 1 }, { document_id: 2 }])
      const note = retrievalSourceDiversityNote(div, new Map())
      expect(note).toMatch(/2 distinct/)
    })
  })
})
