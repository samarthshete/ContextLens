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
| **Code** | `app/queue/full_run.py` (enqueue + `find_primary_job_for_run`), `app/workers/full_run_worker.py` (job + lock), `app/services/run_create.py` (`run_full_benchmark_pipeline`), `app/services/run_requeue.py` (structural eligibility + HTTP re-enqueue), `app/services/run_queue_status.py` (`GET /runs/{id}/queue-status`). |

**Queue name:** `contextlens_full_run`  
**Env:** `REDIS_URL` (default `redis://localhost:6379/0` in `app/config.py`)

### 1b. HTTP queue inspection (`GET /api/v1/runs/{run_id}/queue-status`)

Operator snapshot (no run row mutation, no enqueue). **Redis:** may **delete** a **stale** full-run lock when the best-effort RQ job for this `run_id` is terminal **`failed`** / **`stopped`** / **`canceled`** and the DB row is still **`running`** or **`failed`** (worker died without running the job’s `finally` lock release). Same reconciliation runs before **`POST /requeue`** lock checks.

| Field | Meaning |
|--------|---------|
| `pipeline` | `heuristic` \| `full` — same inference as requeue (heuristic-only trace → `heuristic`; otherwise `full`). |
| `run_status` | Current `runs.status` from PostgreSQL. |
| `lock_present` | Whether Redis key `contextlens:full_run_lock:{run_id}` exists after any stale-lock cleanup. |
| `job_id` / `rq_job_status` | Best-effort: newest RQ job in `contextlens_full_run` whose first argument is `run_id`. **`job_id` is not stored on the run row**; jobs may be missing after TTL or registry cleanup. RQ scan errors are logged and surfaced as nulls (no **500** from the scan path). |
| `requeue_eligible` | `true` only if structural requeue rules pass **and** no lock — does **not** verify `OPENAI_API_KEY` / `CLAUDE_API_KEY` (per `LLM_PROVIDER`) or that enqueue will succeed. |
| `detail` | Why requeue is blocked (structural) or lock message when lock blocks requeue. |

**503** if Redis is unreachable and the run is **`pipeline=full`** (inspection requires Redis). **Heuristic** runs return **200** without calling Redis.

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
| **Redis down at enqueue but run row committed** | Rare race if Redis fails after commit: run can stay **`running`**; fix Redis, then **`POST /api/v1/runs/{run_id}/requeue`** (eligible states only) or enqueue manually via `rq`/scripts. |
| **Stuck / lost job after commit** | Use **`POST /api/v1/runs/{run_id}/requeue`** when the run is **`running`**, **`retrieval_completed`**, **`generation_completed`**, or **`failed`**, not **`completed`**, not heuristic-only, no active **`contextlens:full_run_lock:{run_id}`**, and the **active LLM provider** API key is set (**`OPENAI_API_KEY`** by default, or **`CLAUDE_API_KEY`** if **`LLM_PROVIDER=anthropic`**) — returns **202** + new **`job_id`**. **`failed`** rows are **rewritten** to a resumable status (from `generation_results` / `retrieval_results`) before enqueue so the worker is not a no-op. |

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

After changing **`backend/pyproject.toml`** dependencies (e.g. adding **`openai`**), rebuild: **`docker compose build --no-cache`** then **`up`**. **`backend`** and **`worker`** share one image (**`contextlens-backend:latest`**), so you do not need separate worker rebuilds.

Starts **db**, **redis**, **backend** (container **:8000**, host **:8002**), **worker**. **`docker-compose.yml`** passes **`OPENAI_API_KEY`**, **`LLM_PROVIDER`**, and optional **`CLAUDE_API_KEY`** from the host into **backend** and **worker**; without the key for the active provider, full runs will fail at generation/judge.

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

1. [ ] `cd backend && python scripts/check_redis_for_rq.py` → OK (exit **0**)  
2. [ ] `redis-cli -u "$REDIS_URL" ping` → `PONG`  
3. [ ] Worker process logs show `Listening on contextlens_full_run` (or RQ equivalent)  
4. [ ] `POST /api/v1/runs` with `eval_mode=full` → **202** + `job_id`  
5. [ ] `GET /api/v1/runs/{id}` transitions: `running` → `retrieval_completed` → `generation_completed` → `completed` (or `failed` on bad key / exhausted retries)  
6. [ ] **Benchmark UI:** start a **full** run from **Run benchmark** → **Run detail** shows status progression; **Queue & requeue** shows **`GET /runs/{id}/queue-status`** fields (refresh); when eligible, **`POST /requeue`** via **Requeue full run** succeeds and status refreshes  
7. [ ] **Restart API** mid-run → worker still completes run  
8. [ ] **Stop worker** mid-run → after TTL / retry, behavior matches RQ (may retry or fail; inspect Redis/RQ)  
9. [ ] **Recovery spot-check (optional):** with worker stopped after **202**, confirm run can sit mid-pipeline; start worker **or** use **requeue** when **`requeue_eligible`** is **true** and the **LLM** key for **`LLM_PROVIDER`** is set — run should progress or **503**/**409** matches docs

### 5b. Automated regression (CI / no Redis required)

These do **not** replace the checklist above but catch API contract / eligibility regressions:

```bash
cd backend && pytest tests/test_run_queue_status_api.py tests/test_run_requeue_api.py tests/test_full_run_failure_and_lock.py tests/test_dashboard_summary_api.py -q
```

```bash
docker compose config -q   # repo root — validates Compose file
```

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

---

## 8. Phase 4 ops validation log

Use this table to record **evidence** per environment (staging, prod-like, laptop, CI). **Do not** mark an environment “done” without notes or command output you can point to.

| Environment | Date | Stack | Full run result | Queue status result | Requeue / recovery result | Notes |
|---|---|---|---|---|---|---|
| Local Docker (Mac) | 2026-03-21 | Docker Compose: backend, worker, db, redis; frontend via Vite on localhost:5173; backend on localhost:8002; `LLM_PROVIDER=openai` | **PASS** — full run completed successfully (`run_id=3`) | **PASS** — Run detail showed `pipeline=full`, `job_id=…`, `rq_job_status=finished`, `lock_present=no`, `requeue_eligible=no`, detail `Run is already completed.` | **PARTIAL** — worker stop/start path exercised; no interrupted in-flight full run recovered via UI in this session | E2E OpenAI path: generation, LLM judge, cost, queue-status refresh, completed-run requeue **409**. |
| Local Docker (Mac) | 2026-03-21 | Docker Compose | **PASS** — heuristic (`run_id=1`) | **PASS** — heuristic queue copy | N/A | |
| Local Docker (Mac) | 2026-03-21 | Docker Compose | **PASS** — full completed (`run_id=2`) | **PASS** — `requeue_eligible=false` (incl. frontend refresh) | **PASS** — `POST /requeue` **409** | |
| Local Docker (Mac) | 2026-03-21 | Docker Compose | **PARTIAL** — interrupted full run (`run_id=4`, worker stopped mid-job) | **FAIL (pre-fix)** — queue-status **500** / broken failure path | **FAIL (pre-fix)** — **409** lock + run stuck **`running`** | **Fixed in repo:** `mark_run_failed_sync` → sync **psycopg** (no `asyncio.run`); stale-lock reconcile when RQ job **`failed`/`stopped`/`canceled`**; **re-validate** this row after deploy. |
| **Repo / CI (automated)** | 2026-03-21 | `pytest` | — | — | — | **`138`** backend tests green; queue/requeue, **`test_dashboard_summary_api`**, **`test_dashboard_analytics_api`**, **`test_full_run_failure_and_lock`**; not a substitute for live §5 E2E. |
| Local Docker (Mac) | 2026-03-21 | Docker Compose; interrupted run `run_id=116` | PASS — failed / retry state | PASS — `GET …/queue-status` **200**, `rq_job_status=scheduled`, lock held, `requeue_eligible=false` | PASS — **409** requeue while retry pending | Confirms queue-status stability + correct **409** under active lock/retry. |
| Local Docker (Mac) | 2026-03-21 | Docker Compose (backend, db, redis); host Vite **:5173** → proxy **:8002** | PASS — `seed_benchmark.py` + **6** heuristic traced runs (`run_benchmark.py --eval-mode heuristic` in container) | N/A | N/A | **Phase 6 live dashboard loop:** **`GET /health` 200**. **`GET /api/v1/runs/dashboard-summary`** + **`GET /api/v1/runs/dashboard-analytics`** **200** (sensible empty JSON, then populated). **`docker compose restart backend`** fixed **404** on **`/dashboard-analytics`** when uvicorn had stale routes. **`curl` to `127.0.0.1:5173/api/v1/runs/dashboard-*`** verified Vite proxy. **`DashboardPanel`** states: Vitest + real JSON; **headed browser** not recorded here. |
| Local Docker (Mac) | 2026-03-22 | Docker Compose: backend, worker, db, redis; frontend via Vite | PASS — dashboard summary endpoint returns 200 and populated metrics for a real full run | PASS — interrupted-run queue-status remains stable and consistent with prior run_id=116 behavior | PASS — manual requeue correctly returns 409 while retry/lock is still active; do not claim 202 recovery | Dashboard validated with run_id=322 (`total_runs=1`, `completed=1`, `failed=0`, `in_progress=0`, `llm_runs=1`, `heuristic_runs=0`, `failure_type_counts` includes `RETRIEVAL_MISS: 1`). Remaining gap: no observed post-retry manual requeue recovery PASS yet. |

### Interrupted-run recovery (code vs ops)

- **Code** — validated by tests: interrupted full-run failure marking, stale-lock reconciliation, queue-status safety, and requeue lock handling are covered in automated backend tests.
- **Ops — validated (this environment)**: Completed full runs; **`GET /api/v1/runs/dashboard-summary`** **200** with populated metrics (**run `322`** — see §8 table row **2026-03-22**). **`GET /api/v1/runs/323/queue-status`** for a **completed** full run: `pipeline="full"`, `lock_present=false`, `requeue_eligible=false`, detail **`Run is already completed.`** Prior **`run_id=116`** row remains the logged case for in-flight interrupt + lock/retry + **409** requeue while active.
- **Not interrupt/recovery evidence:** Recent “interruption” attempts were **invalid** for validation (worker stopped **after** the chosen run had **already completed**, and/or **wrong `run_id`** from placeholder/shell-variable mistakes). **No** new PASS for manual **202** recovery; do not infer recovery coverage from those tries.
- **Remaining validation gap**: Still **no** recorded case where a **genuinely interrupted** full run becomes **requeue-eligible** and is recovered via **`POST /api/v1/runs/{id}/requeue` → `202`** through completion. Add a §8 row when that is observed end-to-end.