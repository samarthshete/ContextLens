import { useEffect, useState } from 'react'
import { fetchApiMeta, verifyWriteKey } from '../api/client'
import { getStoredWriteKey, setStoredWriteKey } from '../lib/writeKeyStorage'

/**
 * When the API reports write protection, prompt for the shared write key (sessionStorage).
 * Read-only browsing works without the key; writes return 403 until unlocked.
 */
export function WriteKeyBanner() {
  const [metaLoaded, setMetaLoaded] = useState(false)
  const [writeProtection, setWriteProtection] = useState(false)
  const [hasSessionKey, setHasSessionKey] = useState(() => Boolean(getStoredWriteKey()))
  const [modalOpen, setModalOpen] = useState(false)
  const [candidate, setCandidate] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    let cancelled = false
    fetchApiMeta()
      .then((m) => {
        if (cancelled) return
        setWriteProtection(Boolean(m.write_protection))
        setMetaLoaded(true)
      })
      .catch(() => {
        if (cancelled) return
        setMetaLoaded(true)
        setWriteProtection(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setBusy(true)
    try {
      const ok = await verifyWriteKey(candidate.trim())
      if (!ok) {
        setError('Invalid key or server rejected the request.')
        return
      }
      setStoredWriteKey(candidate.trim())
      setCandidate('')
      setModalOpen(false)
      setHasSessionKey(true)
    } finally {
      setBusy(false)
    }
  }

  if (!metaLoaded || !writeProtection || hasSessionKey) return null

  return (
    <>
      <div
        className="cl-write-key-banner"
        role="status"
        data-testid="write-key-banner"
      >
        <span>
          <strong>Read-only mode</strong> — the API requires a write key for uploads, runs, registry
          edits, and requeue.{' '}
        </span>
        <button type="button" className="cl-write-key-banner__btn" onClick={() => setModalOpen(true)}>
          Enter write key
        </button>
      </div>
      {modalOpen && (
        <div
          className="cl-write-key-modal-backdrop"
          role="presentation"
          onClick={() => !busy && setModalOpen(false)}
        >
          <div
            className="cl-write-key-modal"
            role="dialog"
            aria-labelledby="cl-write-key-title"
            onClick={(ev) => ev.stopPropagation()}
          >
            <h2 id="cl-write-key-title">Unlock writes</h2>
            <p className="cl-write-key-modal__hint">
              Enter the same value as the server <code>CONTEXTLENS_WRITE_KEY</code>. Stored in this
              browser tab only (session).
            </p>
            <form onSubmit={onSubmit}>
              <label className="cl-write-key-modal__label" htmlFor="cl-write-key-input">
                Write key
              </label>
              <input
                id="cl-write-key-input"
                type="password"
                autoComplete="off"
                className="cl-write-key-modal__input"
                value={candidate}
                onChange={(ev) => setCandidate(ev.target.value)}
                disabled={busy}
              />
              {error && <p className="cl-write-key-modal__error">{error}</p>}
              <div className="cl-write-key-modal__actions">
                <button type="submit" disabled={busy || !candidate.trim()}>
                  {busy ? 'Checking…' : 'Save'}
                </button>
                <button type="button" disabled={busy} onClick={() => setModalOpen(false)}>
                  Cancel
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </>
  )
}
