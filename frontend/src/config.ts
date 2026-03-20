/**
 * API base path. Default `/api/v1` uses the Vite dev proxy (`vite.config.ts` → `BACKEND_PROXY_TARGET`, default :8002).
 * Override with `VITE_API_BASE=http://127.0.0.1:8002/api/v1` to bypass the proxy (ensure CORS).
 */
const raw = import.meta.env.VITE_API_BASE as string | undefined
export const API_BASE = (raw?.replace(/\/$/, '') || '/api/v1').trim()
