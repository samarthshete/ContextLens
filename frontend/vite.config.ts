import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  // Loaded from frontend/.env, .env.local, .env.[mode].local, etc.
  const env = loadEnv(mode, process.cwd(), '')
  const target =
    (env.BACKEND_PROXY_TARGET && env.BACKEND_PROXY_TARGET.trim()) ||
    'http://127.0.0.1:8002'

  return {
    plugins: [react()],
    server: {
      proxy: {
        // Same-origin `/api/v1/*` → FastAPI (see `src/config.ts` default API_BASE)
        '/api': {
          target,
          changeOrigin: true,
        },
      },
    },
  }
})
