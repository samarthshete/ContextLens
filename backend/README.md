# ContextLens Backend

FastAPI backend for the ContextLens RAG evaluation and debugging platform.

## Setup

```bash
pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --reload
```

### Full benchmark jobs (Redis + RQ)

`eval_mode=full` on **`POST /api/v1/runs`** enqueues work on queue **`contextlens_full_run`**. Jobs live in **Redis**; a **separate worker** must run the pipeline. See **`../docs/DEV_FULL_RUN_QUEUE.md`** for failure handling, restart safety, and an **E2E verification checklist**.

**Quick pre-flight:**

```bash
cd backend && python scripts/check_redis_for_rq.py
```

**Minimal local setup**

1. Start Redis (e.g. `docker compose up redis -d` from repo root, or `docker run -p 6379:6379 redis:7-alpine`).
2. Set **`REDIS_URL`** (default `redis://localhost:6379/0`) for **both** API and worker.
3. Set **`DATABASE_URL`** to the **same** database the API uses. If Postgres is **Docker Compose** with host port **5433**, use `postgresql+asyncpg://postgres:postgres@localhost:5433/contextlens` from the host.
4. From `backend/`:

```bash
export REDIS_URL=redis://localhost:6379/0
export DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/contextlens
rq worker contextlens_full_run --url "$REDIS_URL"
```

**Docker Compose** (repo root): `docker compose up` starts **db**, **redis**, **backend** (:8000), and **`worker`** (same image; internal URLs `db:5432`, `redis:6379`).

- **Retries:** RQ **`Retry(max=2)`** → **3 attempts** (initial + 2 retries), backoff **15s / 45s**; exhausted → **`on_failure`** marks run **`failed`** (if not already **`completed`**).
- **503** if Redis is unreachable at enqueue time.

## Health

`GET /health` — returns `{"status": "ok"}`

## Benchmark → metrics (quickstart)

```bash
python scripts/seed_benchmark.py
python scripts/run_benchmark.py
python scripts/run_benchmark.py --eval-mode full   # needs CLAUDE_API_KEY
python scripts/generate_contextlens_metrics.py --format markdown
```

See **`../docs/BENCHMARK_WORKFLOW.md`** and **`../docs/FULL_RAG_EXAMPLE.md`**.

**Inspect a run:** `GET /api/v1/runs/{run_id}` (JSON trace for demos).
