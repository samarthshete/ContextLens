# Durable full runs — Redis, RQ, worker (dev & ops)

This document is the **operational source of truth** for **`eval_mode=full`** on **`POST /api/v1/runs`**: enqueue in the API, execute in a **separate worker**, backed by **Redis**.

---

## 1. Components

| Piece | Role |
|--------|------|
| **Redis** | Job queue storage for RQ; must be running before enqueue. |
| **FastAPI** | Creates `runs` row (`running`), **commits**, enqueues job, returns **202** + `job_id`. |
| **RQ worker** | Process running `rq worker contextlens_full_run`; pulls jobs and runs `full_benchmark_run_job`. |
| **PostgreSQL** | Same **`DATABASE_URL`** as the API (worker uses async pipeline via `asyncio.run`). |
| **Code** | `app/queue/full_run.py` (enqueue), `app/workers/full_run_worker.py` (job + lock), `app/services/run_create.py` (`run_full_benchmark_pipeline`). |

**Queue name:** `contextlens_full_run`  
**Env:** `REDIS_URL` (default `redis://localhost:6379/0` in `app/config.py`)

---

## 2. Failure handling (truthful semantics)

| Situation | Behavior |
|-----------|----------|
| **Transient errors** (e.g. `anthropic.APIError`, many generic exceptions) | **Re-raised** → RQ **retries** up to **3 attempts** (`Retry(max=2)` = 1 run + 2 retries), backoff **15s / 45s**. |
| **`ValueError` / `TypeError`** in pipeline | **No RQ retry** → run marked **`failed`** immediately (`_mark_run_failed_safe`). |
| **Retries exhausted** | RQ **`on_failure`** → `mark_run_failed_sync` → run **`failed`** (unless already **`completed`**). |
| **Terminal run** (`completed` / `failed`) | Pipeline **no-op** (idempotent duplicate job). |
| **Mid-pipeline resume** | After a retry, worker resumes from `running` / `retrieval_completed` / `generation_completed` (separate DB commits per phase). |
| **Redis lock** `contextlens:full_run_lock:{run_id}` | **NX + TTL 3600s** — reduces duplicate concurrent work; second worker exits successfully without changing DB. |
| **Redis down at enqueue** | **503** on `POST /runs` (no job). |
| **Redis down at enqueue but run row committed** | Rare race if Redis fails after commit: run can stay **`running`**; fix Redis and **manually re-enqueue** (no first-party HTTP requeue yet). |

---

## 3. Restart safety

| Event | Expected behavior |
|--------|-------------------|
| **API process restarts** | Jobs remain in **Redis**; worker continues processing; **no** in-process state lost for queued work. |
| **Worker process restarts** | Unfinished job may be retried by RQ or left failed depending on shutdown; lock **TTL expires** (~1h) so another worker can proceed. |
| **Redis wiped** | **Queued jobs lost**; runs already **`running`** may never complete — operational restore from backup or manual cleanup / re-run. |
| **DB only** | Unchanged; trace rows are authoritative for run status. |

Durability is **“survives API restart”**, not “survives Redis data loss.”

---

## 4. Local / dev workflows

### A) Docker Compose (all-in-one)

From repo root:

```bash
docker compose up --build
```

Starts **db**, **redis**, **backend** (:8000), **worker**. Ensure **`CLAUDE_API_KEY`** is passed into **backend** (and **worker** if you inject env) for real LLM calls.

### B) Hybrid: Compose Redis + DB, local API + worker

Common for debugging:

```bash
docker compose up redis db -d
```

- **DB from host:** `DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5433/contextlens` (Compose maps **5433→5432**).
- **Redis:** `REDIS_URL=redis://localhost:6379/0`

Terminal 1 — API:

```bash
cd backend && export DATABASE_URL=... REDIS_URL=redis://localhost:6379/0
uvicorn app.main:app --reload --port 8002
```

Terminal 2 — worker (same env):

```bash
cd backend && export DATABASE_URL=... REDIS_URL=redis://localhost:6379/0
rq worker contextlens_full_run --url "$REDIS_URL"
```

### C) Pre-flight check

```bash
cd backend && python scripts/check_redis_for_rq.py
```

Exits **0** if Redis PING works, **1** otherwise.

---

## 5. End-to-end verification checklist

Do this once per environment after any infra change:

1. [ ] `python scripts/check_redis_for_rq.py` → OK  
2. [ ] `redis-cli -u "$REDIS_URL" ping` → `PONG`  
3. [ ] Worker process logs show `Listening on contextlens_full_run` (or RQ equivalent)  
4. [ ] `POST /api/v1/runs` with `eval_mode=full` → **202** + `job_id`  
5. [ ] `GET /api/v1/runs/{id}` transitions: `running` → `retrieval_completed` → `generation_completed` → `completed` (or `failed` on bad key / exhausted retries)  
6. [ ] **Restart API** mid-run → worker still completes run  
7. [ ] **Stop worker** mid-run → after TTL / retry, behavior matches RQ (may retry or fail; inspect Redis/RQ)

---

## 6. Troubleshooting

| Symptom | Likely cause |
|---------|----------------|
| **503** on full `POST /runs` | Redis not running or wrong **`REDIS_URL`**. |
| **202** but run stuck **`running`** forever | Worker not running, wrong **`DATABASE_URL`**, or worker cannot reach DB/Redis. |
| Duplicate work anxiety | Lock + idempotent pipeline limit damage; still avoid double-**enqueue** for same business intent (UI should not double-submit). |

---

## 7. Related docs

- `backend/README.md` — short queue summary  
- `docs/BENCHMARK_WORKFLOW.md` — HTTP + seed + metrics  
- `DECISIONS.md` — Run inspection API decision (retry / lock / codes)  
- `docker-compose.yml` — **redis**, **worker** services  
