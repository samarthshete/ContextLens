/**
 * API base path. Default `/api/v1` uses the Vite dev proxy (`vite.config.ts` → `BACKEND_PROXY_TARGET`, default :8002).
 * For production-like static hosting, set `VITE_API_BASE=https://<api-host>/api/v1` at build time and configure
 * backend `CORS_ORIGINS` to include the SPA origin (`docs/DEPLOYMENT.md`).
 */
const raw = import.meta.env.VITE_API_BASE as string | undefined
export const API_BASE = (raw?.replace(/\/$/, '') || '/api/v1').trim()
