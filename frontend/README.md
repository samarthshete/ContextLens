# ContextLens frontend

React + TypeScript + Vite. **Primary screen:** benchmark execution and inspection against the existing FastAPI backend.

## Dev setup

1. Start PostgreSQL + backend (e.g. `cd backend && uvicorn app.main:app --reload --port 8002`).
2. `npm install && npm run dev` → [http://localhost:5173](http://localhost:5173)

`vite.config.ts` proxies **`/api/*`** to **`BACKEND_PROXY_TARGET`** (default **`http://127.0.0.1:8002`**), so the browser calls **`/api/v1/...`** same-origin (no CORS friction).

- **Docker Compose** on host port **8000**: create `frontend/.env.development.local` with  
  `BACKEND_PROXY_TARGET=http://127.0.0.1:8000`
- **Bypass proxy** (direct to API; needs CORS):  
  `VITE_API_BASE=http://127.0.0.1:8002/api/v1 npm run dev`

See **`.env.example`** in this folder.

## What the UI does

| Tab | APIs used |
|-----|-----------|
| **Run benchmark** | `GET /datasets`, `GET /query-cases?dataset_id=`, `GET /pipeline-configs`, `GET /documents`, `POST /runs` |
| **Recent runs** | `GET /runs` |
| **Run detail** | `GET /runs/{id}` |
| **Config comparison** | `GET /runs/config-comparison` |

Seed benchmark data first (`backend/scripts/seed_benchmark.py` + corpus / `run_benchmark` or uploads) so dropdowns are non-empty.

## Build

```bash
npm run build
```

## Tests (unit)

```bash
npm run test
```

Covers pure helpers (`formValidation`, API error copy). End-to-end flow: run backend + `npm run dev`, then exercise all tabs against real data.
