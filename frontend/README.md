# ContextLens frontend

React + TypeScript + Vite. **Primary screen:** benchmark execution and inspection against the existing FastAPI backend.

## Dev setup

1. Start PostgreSQL + API — either **`docker compose up --build`** (API on host **http://127.0.0.1:8002**) **or** `cd backend && uvicorn app.main:app --reload --port 8002` (**not** both on **8002**).
2. `npm install && npm run dev` → [http://localhost:5173](http://localhost:5173)

`vite.config.ts` proxies **`/api/*`** to **`BACKEND_PROXY_TARGET`** (default **`http://127.0.0.1:8002`**), matching the **Compose `backend`** port mapping **8002:8000**.

- **API on a non-default port:** set `BACKEND_PROXY_TARGET=...` in `frontend/.env.development.local`.
- **Bypass proxy** (direct to API; needs CORS):  
  `VITE_API_BASE=http://127.0.0.1:8002/api/v1 npm run dev`

See **`.env.example`** in this folder.

## What the UI does

| Tab | APIs used |
|-----|-----------|
| **Run benchmark** | `GET /datasets`, `GET /query-cases?dataset_id=`, `GET /pipeline-configs`, `GET /documents`, `POST /runs` |
| **Recent runs** | `GET /runs` |
| **Run detail** | `GET /runs/{id}`, `GET /runs/{id}/queue-status`, `POST /runs/{id}/requeue` (eligible full runs) |
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
