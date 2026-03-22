# ContextLens — deployment (production-like)

This document describes a **minimal, honest** path to host ContextLens for a **public demo** or **internal single-tenant** use. It is **not** enterprise multi-tenant SaaS hardening.

**Stack shape (default):**

| Piece | Suggested platform |
|--------|-------------------|
| Frontend (Vite SPA) | Vercel (static) or Netlify |
| Backend API | Render or Railway (Web service) |
| Worker (RQ) | Same provider as API, **second process**, same image/env as API |
| PostgreSQL + pgvector | Managed Postgres on same provider (or Neon + enable pgvector if supported) |
| Redis | Managed Redis / Valkey |

Docker Compose remains the **local** reference; production-like hosts usually run **API** and **worker** as two services from the same container image with the **same** environment variables for DB, Redis, and LLM keys.

---

## 1. Topology

```
Browser → HTTPS → Static SPA (Vercel)
                 ↓ VITE_API_BASE=https://api.example.com/api/v1
                 → HTTPS → FastAPI (Render/Railway)
                              ↓ same DATABASE_URL, REDIS_URL
                           RQ worker process (full benchmark runs)
```

- **API** and **worker** must share:
  - `DATABASE_URL` (async URL, e.g. `postgresql+asyncpg://…`)
  - `REDIS_URL` (same logical DB index as used for enqueue)
  - `LLM_PROVIDER`, `OPENAI_API_KEY` / `CLAUDE_API_KEY` (for `eval_mode=full`)
- **Worker command** (same as local):  
  `rq worker contextlens_full_run --url $REDIS_URL`  
  (Working directory / image must include the `backend` app and dependencies.)

---

## 2. Environment variables

### Backend / worker (shared)

| Variable | Required | Notes |
|----------|----------|--------|
| `DATABASE_URL` | Yes | `postgresql+asyncpg://user:pass@host:5432/db` (managed hosts often supply `postgresql://…`; the app coerces to `+asyncpg` — §9.5) |
| `REDIS_URL` | Yes for full RAG queue | e.g. `redis://:pass@host:6379/0` |
| `CORS_ORIGINS` | Yes (hosted) | Comma-separated **exact** origins, e.g. `https://my-app.vercel.app` — **no** `*` when `APP_ENV=production` |
| `APP_ENV` | Recommended | `development` (default) vs `production` for strict checks |
| `CONTEXTLENS_WRITE_KEY` | Recommended (public demo) | Non-empty enables write protection (see §4) |
| `LLM_PROVIDER` | For full runs | `openai` (default) or `anthropic` |
| `OPENAI_API_KEY` / `CLAUDE_API_KEY` | When using that provider | Never commit; set in host UI only |
| `UPLOAD_DIR` | Optional | Writable path in container (default `uploads`) |

### Frontend (build-time)

| Variable | Purpose |
|----------|---------|
| `VITE_API_BASE` | Full URL to API prefix, e.g. `https://api.example.com/api/v1` (no trailing slash). **Required** when SPA and API are on different origins. |

Do **not** put `CONTEXTLENS_WRITE_KEY` in `VITE_*` — the UI prompts for it at runtime and stores it in **sessionStorage** (see §4).

### Strict `APP_ENV=production`

When `APP_ENV=production`, the API **fails fast** on startup if:

- `CONTEXTLENS_WRITE_KEY` is empty, or  
- `CORS_ORIGINS` is empty or contains `*`.

Use this for **internet-facing** API processes. For relaxed internal hosts, keep `APP_ENV=development` (default) and still set `CONTEXTLENS_WRITE_KEY` if you want the write gate.

---

## 3. CORS and API URL

- Backend allows origins from `CORS_ORIGINS` only (comma-separated).
- Frontend must use `VITE_API_BASE` pointing at the **public API URL** so the browser calls the API directly (CORS + preflight for `X-ContextLens-Write-Key` when used).
- Local dev keeps default `VITE_API_BASE` unset and uses the Vite proxy (`/api` → `BACKEND_PROXY_TARGET`).

---

## 4. Write protection (demo gate)

**Not** user accounts — a single shared secret:

- If `CONTEXTLENS_WRITE_KEY` is set, every **non-GET/HEAD/OPTIONS** request under `/api/v1` must send header:
  - `X-ContextLens-Write-Key: <same value>`
- **GET** remains allowed without the key (read-only browsing: runs list, dashboard, run detail).
- Public metadata:
  - `GET /api/v1/meta` → `{ "write_protection": bool, "app_env": string }`
  - `POST /api/v1/meta/verify-write-key` with the header → `{"ok": true}` if the key matches (used by the UI unlock flow).
- `GET /health` → `{ "status": "ok", "write_protection": bool }`

**Limitations (honest):**

- Anyone who knows the key can write; the key in sessionStorage can be exfiltrated via XSS.
- For stronger isolation, put the API on a private network or add **edge** auth (e.g. Basic Auth at the reverse proxy) — out of scope for this repo pass.

When `APP_ENV=production`, an empty `CONTEXTLENS_WRITE_KEY` is **rejected** at startup so you cannot accidentally expose writes.

---

## 5. OpenAPI / docs

When `APP_ENV=production`, `/docs`, `/redoc`, and `/openapi.json` are **disabled** on the API.

---

## 6. SPA routing (Vercel / static hosts)

The app uses **client-side routing** (`react-router-dom`). The static host must serve `index.html` for non-file paths.

- **Vercel:** `frontend/vercel.json` includes rewrites for this repo.
- **nginx:** `try_files $uri $uri/ /index.html;` for the frontend root.

---

## 7. Database migrations

Run Alembic against the **same** `DATABASE_URL` before or right after first deploy:

```bash
cd backend && alembic upgrade head
```

(On Render/Railway, use a one-off command or release phase.)

---

## 8. Smoke-test checklist (after deploy)

Use your real URLs. Mark items **read-only** vs **write** (needs unlock + write key if enabled).

1. [ ] **Frontend** — SPA loads (no blank screen; no infinite redirect).
2. [ ] **`GET /health`** — `200`, JSON includes `status`.
3. [ ] **`GET /api/v1/meta`** — `200`; `write_protection` matches expectation.
4. [ ] **CORS** — Browser devtools: no CORS errors on `GET /api/v1/runs` from the SPA origin.
5. [ ] **Runs list** — `/runs` loads (GET).
6. [ ] **Dashboard** — `/dashboard` loads summary + analytics (GET).
7. [ ] **Run detail** — `/runs/{id}` loads for an existing id (GET).
8. [ ] **Queue browser** — `/queue` loads (GET-only paths).
9. [ ] **Write gate** — With `CONTEXTLENS_WRITE_KEY` set: banner appears; after unlock, **POST** run or upload works; without key, POST returns **403** `write_key_required`.
10. [ ] **Full run** — Create `eval_mode=full` run (after unlock); **worker** picks up job; run completes or fails visibly in UI.
11. [ ] **Requeue** — For an eligible failed/stuck full run, requeue returns **202** (with key if write protection on).
12. [ ] **Secrets** — Repo / build logs do not contain API keys or `CONTEXTLENS_WRITE_KEY`.

---

## 9. Vercel + Render (concrete mapping)

This section pins **one** reproducible shape: **Vercel** (SPA) + **Render** (API + worker + Postgres + Key Value). It does **not** mean the repo owners have executed a deploy in your account — follow the steps below.

### 9.1 Service topology (exact)

| Render resource | Blueprint `name` | Type | Purpose |
|-----------------|-------------------|------|---------|
| `contextlens-pg` | `contextlens-pg` | **PostgreSQL 16** | Primary DB; **pgvector** via `CREATE EXTENSION vector` in Alembic (`0002_add_embedding_to_chunks.py`). Render supports pgvector ([extensions doc](https://render.com/docs/postgresql-extensions)). |
| `contextlens-redis` | `contextlens-redis` | **Key Value** (`type: keyvalue`) | Redis-compatible URL for RQ; `REDIS_URL` = internal `connectionString`. |
| `contextlens-api` | `contextlens-api` | **Web service**, `runtime: docker` | FastAPI; `rootDir: backend`, `Dockerfile` CMD = `uvicorn app.main:app --host 0.0.0.0 --port 8000`. |
| `contextlens-worker` | `contextlens-worker` | **Background worker**, `runtime: docker` | Same image as API; `dockerCommand: ./scripts/rq_worker.sh` → `rq worker contextlens_full_run --url $REDIS_URL`. |

**Vercel:** one **Static Site** / framework project with **Root Directory** = `frontend` (the directory that contains `package.json` and `vercel.json`).

### 9.2 Frontend (Vercel) — exact settings

| Field | Value |
|--------|--------|
| **Root Directory** | `frontend` |
| **Framework** | Vite (auto-detected or set manually) |
| **Build Command** | `npm run build` (default; matches `frontend/vercel.json`) |
| **Output Directory** | `dist` (matches `frontend/vercel.json`) |
| **Environment variables (Production)** | `VITE_API_BASE` = `https://<your-render-api-hostname>/api/v1` — **no trailing slash**. Example: `https://contextlens-api.onrender.com/api/v1`. |

`frontend/vercel.json` sets SPA **rewrites** so client routes (`/runs`, `/dashboard`, …) resolve to `index.html`.

### 9.3 Backend API (Render web service)

| Field | Value |
|--------|--------|
| **Service type** | Web Service |
| **Runtime** | Docker |
| **Root directory** | `backend` |
| **Dockerfile path** | `Dockerfile` |
| **Health check path** | `/health` |
| **Pre-deploy command** | `alembic upgrade head` (runs in the built image; requires `alembic/` + `alembic.ini` in the image — see `backend/Dockerfile`) |

### 9.4 Worker (Render background worker)

| Field | Value |
|--------|--------|
| **Service type** | Background Worker |
| **Runtime** | Docker |
| **Same** `rootDir` / `Dockerfile` as API | Yes |
| **Start command** | `./scripts/rq_worker.sh` (equivalent to `rq worker contextlens_full_run --url "$REDIS_URL"`) |

**Env parity (required on worker):** same `DATABASE_URL`, `REDIS_URL`, `LLM_PROVIDER`, and **same** provider API keys as the API for `eval_mode=full`. The sample `render.yaml` uses env group **`contextlens-llm`** so `OPENAI_API_KEY` / `CLAUDE_API_KEY` are defined once and attached to both services.

### 9.5 Database URL (Render → asyncpg)

Render’s Postgres **`connectionString`** uses `postgresql://…`. The app **normalizes** that to `postgresql+asyncpg://…` at settings load (`app.config.normalize_async_database_url`). You may still set `DATABASE_URL` manually with `postgresql+asyncpg://` if you prefer.

### 9.6 Environment variable map (deployment)

**Backend web + worker (Render)** — names match `app.config` / `.env.example`:

| Variable | API | Worker | Source / notes |
|----------|-----|--------|----------------|
| `DATABASE_URL` | ✓ | ✓ | `fromDatabase` → `connectionString` (coerced to `+asyncpg` in app) |
| `REDIS_URL` | ✓ | ✓ | `fromService` Key Value → `connectionString` |
| `APP_ENV` | ✓ | optional | `production` for strict CORS + write key + disabled OpenAPI |
| `CORS_ORIGINS` | ✓ | — | Comma-separated; **must** include exact Vercel URL(s), e.g. `https://foo.vercel.app` |
| `CONTEXTLENS_WRITE_KEY` | ✓ | — | Non-empty required when `APP_ENV=production`; Blueprint may `generateValue: true` |
| `LLM_PROVIDER` | ✓ | ✓ | `openai` (default) or `anthropic` |
| `OPENAI_API_KEY` | ✓ | ✓ | `sync: false` / Dashboard secret |
| `CLAUDE_API_KEY` | ✓ | ✓ | If `LLM_PROVIDER=anthropic` |
| `UPLOAD_DIR` | ✓ | ✓ | Writable path; e.g. `/tmp/contextlens-uploads` (ephemeral on Render) |
| `OPENAI_INPUT_USD_PER_MILLION_TOKENS` | ✓ | ✓ | Optional; defaults in `config.py` |
| `OPENAI_OUTPUT_USD_PER_MILLION_TOKENS` | ✓ | ✓ | Optional |
| `ANTHROPIC_*` pricing | ✓ | ✓ | Optional |

**Frontend (Vercel build):**

| Variable | Required |
|----------|----------|
| `VITE_API_BASE` | **Yes** for cross-origin production (full URL including `/api/v1`) |

### 9.7 Deploy order (runbook)

1. **Create Render resources** — e.g. **Blueprint** from `render.yaml`, or create Postgres + Key Value + Web + Worker manually with the same env wiring.
2. **Wait for Postgres** to be available.
3. **First API deploy** — `preDeployCommand` runs **`alembic upgrade head`** (creates schema + `vector` extension).
4. **Set Dashboard secrets** — `CORS_ORIGINS`, `OPENAI_API_KEY` (group `contextlens-llm` if using the Blueprint), confirm `CONTEXTLENS_WRITE_KEY` (copy for trusted operators / SPA unlock).
5. **Redeploy API** if you changed env after failed boot (e.g. missing CORS).
6. **Deploy worker** — same image/env group so it can process RQ jobs.
7. **Create Vercel project** — root `frontend`, set `VITE_API_BASE` to `https://<render-api>/api/v1`, deploy.
8. **Update `CORS_ORIGINS`** on Render if the Vercel preview/production URL was not known at step 4; redeploy API.

**Manual migration (if you skip `preDeployCommand`):** Shell into a one-off environment or use Render **Shell** for the API service, `cd` to app root, run `alembic upgrade head` with `DATABASE_URL` set (same as service).

### 9.8 Post-deploy smoke checklist (concrete)

Do these in order; use browser devtools **Network** for CORS.

1. [ ] Open Vercel URL `/` → redirects to `/benchmark`; no blank page.
2. [ ] `GET https://<render-api>/health` → **200**, JSON `status`, `write_protection`.
3. [ ] `GET https://<render-api>/api/v1/meta` → **200**, `write_protection` / `app_env`.
4. [ ] Open `/dashboard` on Vercel — data loads or empty state **without** CORS errors.
5. [ ] Open `/runs`, `/queue` — same.
6. [ ] Open `/runs/<id>` for a known run id (or empty list first).
7. [ ] **Write gate:** `POST https://<render-api>/api/v1/datasets` with JSON body **without** `X-ContextLens-Write-Key` → **403** `write_key_required` (when write protection on).
8. [ ] **Unlock:** SPA shows read-only banner; enter `CONTEXTLENS_WRITE_KEY`; `POST /api/v1/meta/verify-write-key` succeeds; subsequent mutating requests include header from sessionStorage.
9. [ ] **Protected write:** after unlock, create dataset or heuristic run → **201** / **200** as applicable.
10. [ ] **Queue:** trigger `eval_mode=full` (needs OpenAI/Anthropic key); worker consumes job; run reaches terminal state in UI.
11. [ ] **Requeue** (optional): eligible full run → **202** with write key on mutating path.

### 10.9 Blockers / limitations (Render-specific)

- **Free Key Value / plan changes:** if `plan: free` for Key Value is unavailable in your workspace, set a paid **starter** plan in the Dashboard or edit `render.yaml`.
- **Cold starts:** Render free/low-tier web services may spin down; first request can be slow.
- **Uploads:** `UPLOAD_DIR` on default disk is **ephemeral** — uploads are lost on restart unless you add a **persistent disk** (not in default Blueprint).
- **This repo does not record a live Render URL** — acceptance is **prep + docs**, not “already deployed” unless you run the steps.

---

## 10. References

- Queue / worker semantics: `docs/DEV_FULL_RUN_QUEUE.md`
- Local Compose: `docker-compose.yml` (backend + worker + db + redis)
- Render Blueprint: `render.yaml` (repository root)
- Project contract: `PROJECT.md`, `DECISIONS.md`, `CURRENT_STATE.md`
