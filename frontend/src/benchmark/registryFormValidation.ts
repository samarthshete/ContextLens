/** Client-side checks aligned with backend registry validation (friendly UX before submit). */

export function validatePipelineChunkParams(
  chunkSize: number,
  chunkOverlap: number,
): { ok: true } | { ok: false; message: string } {
  if (!Number.isFinite(chunkSize) || chunkSize < 1) {
    return { ok: false, message: 'Chunk size must be at least 1.' }
  }
  if (!Number.isFinite(chunkOverlap) || chunkOverlap < 0) {
    return { ok: false, message: 'Chunk overlap cannot be negative.' }
  }
  if (chunkOverlap >= chunkSize) {
    return { ok: false, message: 'Chunk overlap must be strictly less than chunk size.' }
  }
  return { ok: true }
}

export function validateTopK(topK: number): { ok: true } | { ok: false; message: string } {
  if (!Number.isFinite(topK) || topK < 1) {
    return { ok: false, message: 'top_k must be at least 1.' }
  }
  return { ok: true }
}
