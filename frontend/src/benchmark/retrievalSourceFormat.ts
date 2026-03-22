/**
 * Display helpers for retrieval hits — only uses fields present on run detail hits + optional document list.
 */

import type { DocumentListItem } from '../api/types'

export type RetrievalHitForSource = {
  document_id: number
  rank: number
  score: number
  chunk_id: number
  chunk_index: number
}

/** Map document id → title from registry list (may be incomplete). */
export function documentTitleLookupMap(documents: DocumentListItem[]): Map<number, string> {
  const m = new Map<number, string>()
  for (const d of documents) {
    if (d.id != null && typeof d.title === 'string' && d.title.trim() !== '') {
      m.set(d.id, d.title.trim())
    }
  }
  return m
}

/**
 * Human-readable source line for one hit. Does not invent titles — uses lookup only when provided.
 */
export function formatRetrievalDocumentLabel(
  documentId: number,
  titleByDocumentId: Map<number, string>,
): string {
  const title = titleByDocumentId.get(documentId)
  if (title != null && title.length > 0) {
    return `${title} · document #${documentId}`
  }
  return `Document #${documentId}`
}

export type RetrievalSourceDiversity = {
  hitCount: number
  uniqueDocumentCount: number
  /** When all hits share one document, that id; else null */
  singleDocumentId: number | null
}

export function analyzeRetrievalSourceDiversity(
  hits: Array<Pick<RetrievalHitForSource, 'document_id'>>,
): RetrievalSourceDiversity {
  const hitCount = hits.length
  if (hitCount === 0) {
    return { hitCount: 0, uniqueDocumentCount: 0, singleDocumentId: null }
  }
  const ids = hits.map((h) => h.document_id)
  const unique = new Set(ids)
  const uniqueDocumentCount = unique.size
  const singleDocumentId = uniqueDocumentCount === 1 ? ids[0]! : null
  return { hitCount, uniqueDocumentCount, singleDocumentId }
}

/**
 * Short note for above the hit list. Returns null when there is nothing useful to say.
 */
export function retrievalSourceDiversityNote(
  div: RetrievalSourceDiversity,
  titleByDocumentId: Map<number, string>,
): string | null {
  if (div.hitCount === 0) return null
  if (div.uniqueDocumentCount <= 1 && div.hitCount > 1 && div.singleDocumentId != null) {
    const label = formatRetrievalDocumentLabel(div.singleDocumentId, titleByDocumentId)
    return `All ${div.hitCount} top hits are from the same source: ${label}.`
  }
  if (div.uniqueDocumentCount > 1) {
    return `Hits span ${div.uniqueDocumentCount} distinct source documents (by document id).`
  }
  if (div.hitCount === 1 && div.singleDocumentId != null) {
    const label = formatRetrievalDocumentLabel(div.singleDocumentId, titleByDocumentId)
    return `Single hit from ${label}.`
  }
  return null
}
