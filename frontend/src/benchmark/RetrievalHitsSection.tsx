import { Link } from 'react-router-dom'
import type { RunDetail } from '../api/types'
import {
  analyzeRetrievalSourceDiversity,
  formatRetrievalDocumentLabel,
  retrievalSourceDiversityNote,
} from './retrievalSourceFormat'

type Hit = RunDetail['retrieval_hits'][number]

function canOpenDocumentDetail(documentId: number | null | undefined): documentId is number {
  return documentId != null && Number.isFinite(documentId) && documentId > 0
}

export function RetrievalHitsSection({
  hits,
  documentTitleById,
}: {
  hits: Hit[]
  documentTitleById: Map<number, string>
}) {
  return (
    <section className="cl-subsection" data-testid="retrieval-hits-section">
      <h3>Retrieval hits ({hits.length})</h3>
      <p className="cl-muted cl-retrieval-source-hint">
        Source uses <strong>document #id</strong> from the run payload. When an id is present, the label is a
        link to <strong>document detail</strong> (metadata + stored chunks). Titles appear when this session
        has loaded the document list from the Run tab (same registry fetch).
      </p>
      {!hits.length ? (
        <p className="cl-muted">No chunks retrieved.</p>
      ) : (
        <>
          {(() => {
            const div = analyzeRetrievalSourceDiversity(hits)
            const note = retrievalSourceDiversityNote(div, documentTitleById)
            return note ? (
              <p className="cl-muted cl-retrieval-source-note" role="status">
                {note}
              </p>
            ) : null
          })()}
          {hits.map((h) => {
            const docId = h.document_id
            const sourceLabel = canOpenDocumentDetail(docId)
              ? formatRetrievalDocumentLabel(docId, documentTitleById)
              : '—'
            return (
              <div key={h.chunk_id} className="cl-hit" data-testid={`retrieval-hit-${h.rank}`}>
                <div className="cl-hit-meta">
                  <strong>#{h.rank}</strong>
                  <span className="cl-hit-meta-sep" aria-hidden>
                    ·
                  </span>
                  <span>score {h.score.toFixed(4)}</span>
                  <span className="cl-hit-meta-sep" aria-hidden>
                    ·
                  </span>
                  <span className="cl-hit-source">
                    <span className="cl-hit-source-k">Source</span>{' '}
                    {canOpenDocumentDetail(docId) ? (
                      <Link
                        to={`/documents/${docId}`}
                        className="cl-hit-source-link"
                        data-testid={`retrieval-hit-source-link-${h.rank}`}
                      >
                        {sourceLabel}
                      </Link>
                    ) : (
                      <span data-testid={`retrieval-hit-source-plain-${h.rank}`}>{sourceLabel}</span>
                    )}
                  </span>
                  <span className="cl-hit-meta-sep" aria-hidden>
                    ·
                  </span>
                  <span className="cl-tabular-nums">
                    chunk {h.chunk_id} · index {h.chunk_index}
                  </span>
                </div>
                <pre className="cl-pre cl-pre-sm">{h.content}</pre>
              </div>
            )
          })}
        </>
      )}
    </section>
  )
}
