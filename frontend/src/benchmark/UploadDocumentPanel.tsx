import { useRef, useState } from 'react'
import { api } from '../api/client'
import type { DocumentResponse } from '../api/types'
import { describeDocumentUploadError } from './errorMessage'

const ALLOWED_EXT = new Set(['.pdf', '.txt', '.md', '.markdown'])

function fileExtension(name: string): string {
  const i = name.lastIndexOf('.')
  return i >= 0 ? name.slice(i).toLowerCase() : ''
}

type Props = {
  disabled?: boolean
  onDocumentUploaded: (doc: DocumentResponse) => void
}

export function UploadDocumentPanel({ disabled, onDocumentUploaded }: Props) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<File | null>(null)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState(false)

  function onFileChange(ev: React.ChangeEvent<HTMLInputElement>) {
    setError(null)
    setSuccess(false)
    const f = ev.target.files?.[0] ?? null
    setFile(f)
  }

  async function handleUpload() {
    setError(null)
    setSuccess(false)
    if (!file) return
    if (file.size === 0) {
      setError('File is empty.')
      return
    }
    const ext = fileExtension(file.name)
    if (ext && !ALLOWED_EXT.has(ext)) {
      setError('Use PDF, TXT, or Markdown (.md).')
      return
    }

    setUploading(true)
    try {
      const doc = await api.uploadDocument(file)
      onDocumentUploaded(doc)
      setSuccess(true)
      setFile(null)
      if (inputRef.current) inputRef.current.value = ''
    } catch (e) {
      setError(describeDocumentUploadError(e))
    } finally {
      setUploading(false)
    }
  }

  const canUpload = Boolean(file) && !uploading && !disabled

  return (
    <div className="cl-upload-panel">
      <h3 className="cl-upload-title">Upload document</h3>
      <p className="cl-muted cl-upload-hint">
        <code>POST /api/v1/documents</code> — PDF, TXT, or Markdown. Ingests, chunks, and embeds.
      </p>
      <div className="cl-upload-row">
        <input
          ref={inputRef}
          type="file"
          accept=".pdf,.txt,.md,.markdown,application/pdf,text/plain,text/markdown"
          onChange={onFileChange}
          disabled={Boolean(disabled) || uploading}
          aria-label="Choose file to upload"
        />
        <button
          type="button"
          className="cl-btn cl-btn-secondary"
          disabled={!canUpload}
          onClick={() => void handleUpload()}
        >
          {uploading ? (
            <span className="cl-upload-inline">
              <span className="cl-spinner" aria-hidden />
              Uploading…
            </span>
          ) : (
            'Upload'
          )}
        </button>
      </div>
      {error ? (
        <div className="cl-msg cl-msg-error cl-upload-msg" role="alert">
          {error}
        </div>
      ) : null}
      {success ? (
        <div className="cl-msg cl-msg-ok cl-upload-msg" role="status">
          Document uploaded
        </div>
      ) : null}
    </div>
  )
}
