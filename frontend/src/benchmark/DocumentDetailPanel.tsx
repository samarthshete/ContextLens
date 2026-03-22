import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api, ApiError } from '../api/client'
import type { DocumentChunk, DocumentResponse } from '../api/types'
import { describeApiError } from './errorMessage'

function formatJson(v: unknown): string {
  return JSON.stringify(v, null, 2)
}

function formatWhen(iso: string): string {
  try {
    return new Date(iso).toLocaleString()
  } catch {
    return iso
  }
}

export function DocumentDetailPanel() {
  const navigate = useNavigate()
  const params = useParams<{ documentId: string }>()
  const raw = params.documentId ?? ''
  const docIdNum = Number(raw)
  const validId = Number.isFinite(docIdNum) && Number.isInteger(docIdNum) && docIdNum > 0

  const [doc, setDoc] = useState<DocumentResponse | null>(null)
  const [chunks, setChunks] = useState<DocumentChunk[] | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    if (!validId) {
      setLoading(false)
      setError(null)
      setDoc(null)
      setChunks(null)
      return
    }
    setLoading(true)
    setError(null)
    try {
      const [d, ch] = await Promise.all([
        api.getDocument(docIdNum),
        api.getDocumentChunks(docIdNum),
      ])
      setDoc(d)
      setChunks(ch)
    } catch (e) {
      setDoc(null)
      setChunks(null)
      if (e instanceof ApiError && e.status === 404) {
        setError('Document not found.')
      } else {
        setError(describeApiError(e))
      }
    } finally {
      setLoading(false)
    }
  }, [docIdNum, validId])

  useEffect(() => {
    void load()
  }, [load])

  return (
    <section className="cl-card" data-testid="document-detail-panel" aria-labelledby="document-detail-heading">
      <div className="cl-actions" style={{ marginBottom: '1rem' }}>
        <button type="button" className="cl-btn cl-btn-secondary" onClick={() => navigate(-1)}>
          Back
        </button>
      </div>

      <h2 id="document-detail-heading">Document</h2>

      {!validId ? (
        <p className="cl-msg cl-msg-error" role="alert" data-testid="document-detail-invalid">
          Invalid document ID: &quot;{raw}&quot;. Expected a positive integer.
        </p>
      ) : loading ? (
        <p className="cl-loading" aria-live="polite">
          Loading document…
        </p>
      ) : error ? (
        <p className="cl-msg cl-msg-error" role="alert">
          {error}
        </p>
      ) : doc && chunks ? (
        <>
          <section className="cl-subsection" data-testid="document-detail-meta">
            <h3>Metadata</h3>
            <dl className="cl-meta-dl">
              <div>
                <dt>ID</dt>
                <dd>{doc.id}</dd>
              </div>
              <div>
                <dt>Title</dt>
                <dd>{doc.title}</dd>
              </div>
              <div>
                <dt>Status</dt>
                <dd>{doc.status}</dd>
              </div>
              <div>
                <dt>Source type</dt>
                <dd>{doc.source_type}</dd>
              </div>
              <div>
                <dt>Created</dt>
                <dd>{formatWhen(doc.created_at)}</dd>
              </div>
            </dl>
            {doc.metadata_json && Object.keys(doc.metadata_json).length > 0 ? (
              <details className="cl-details">
                <summary>metadata_json</summary>
                <pre className="cl-pre cl-pre-sm">{formatJson(doc.metadata_json)}</pre>
              </details>
            ) : null}
          </section>

          <section className="cl-subsection" data-testid="document-detail-chunks">
            <h3>Chunks ({chunks.length})</h3>
            <p className="cl-muted">
              Full stored chunk texts from <code>GET /api/v1/documents/{'{id}'}/chunks</code> (provenance /
              inspection).
            </p>
            {chunks.length === 0 ? (
              <p className="cl-muted">No chunks on this document.</p>
            ) : (
              <div className="cl-document-chunk-list">
                {chunks.map((c) => (
                  <article
                    key={c.id}
                    className="cl-document-chunk"
                    data-testid={`document-chunk-${c.chunk_index}`}
                  >
                    <div className="cl-hit-meta">
                      <strong>index {c.chunk_index}</strong>
                      <span className="cl-hit-meta-sep" aria-hidden>
                        ·
                      </span>
                      <span className="cl-tabular-nums">chunk id {c.id}</span>
                      {c.start_char != null && c.end_char != null ? (
                        <>
                          <span className="cl-hit-meta-sep" aria-hidden>
                            ·
                          </span>
                          <span className="cl-tabular-nums">
                            chars {c.start_char}–{c.end_char}
                          </span>
                        </>
                      ) : null}
                    </div>
                    <pre className="cl-pre cl-pre-sm">{c.content}</pre>
                  </article>
                ))}
              </div>
            )}
          </section>
        </>
      ) : null}
    </section>
  )
}
