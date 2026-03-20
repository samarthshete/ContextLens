import { beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from './client'

describe('api.uploadDocument', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
  })

  it('POSTs multipart FormData and default chunk query params', async () => {
    const mockJson = {
      id: 42,
      title: 'notes.txt',
      source_type: 'txt',
      status: 'processed',
      metadata_json: null,
      created_at: '2025-01-01T00:00:00Z',
    }
    vi.mocked(fetch).mockResolvedValue({
      ok: true,
      status: 201,
      json: async () => mockJson,
    } as Response)

    const file = new File(['hello'], 'notes.txt', { type: 'text/plain' })
    const doc = await api.uploadDocument(file)

    expect(doc).toEqual(mockJson)
    expect(fetch).toHaveBeenCalledTimes(1)
    const [url, init] = vi.mocked(fetch).mock.calls[0]
    expect(String(url)).toContain('/documents?')
    expect(String(url)).toContain('chunk_strategy=fixed')
    expect(String(url)).toContain('chunk_size=512')
    expect(String(url)).toContain('chunk_overlap=0')
    expect(init?.method).toBe('POST')
    expect(init?.body).toBeInstanceOf(FormData)
    const fd = init?.body as FormData
    expect(fd.get('file')).toBe(file)
  })

  it('throws ApiError on failure', async () => {
    vi.mocked(fetch).mockResolvedValue({
      ok: false,
      status: 413,
      json: async () => ({ detail: 'File too large.' }),
    } as Response)

    const file = new File(['x'], 'big.pdf', { type: 'application/pdf' })
    await expect(api.uploadDocument(file)).rejects.toMatchObject({
      status: 413,
      detail: 'File too large.',
    })
  })
})
