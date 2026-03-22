# ContextLens Backend

FastAPI backend for the ContextLens RAG evaluation and debugging platform.

## Setup

```bash
pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --reload --port 8002
```

Set **`OPENAI_API_KEY`** (and **`LLM_PROVIDER=openai`**, default) for **`eval_mode=full`**. For **Anthropic**, set **`LLM_PROVIDER=anthropic`** and **`CLAUDE_API_KEY`**. Env template: **`backend/.env.example`** or repo root **`.env.example`**.

**Docker Compose** exposes the API on host **http://127.0.0.1:8002** (`8002:8000`). Avoid running this **and** local uvicorn both bound to **8002**.

### Full benchmark jobs (Redis + RQ)

`eval_mode=full` on **`POST /api/v1/runs`** enqueues work on queue **`contextlens_full_run`**. Jobs live in **Redis**; a **separate worker** must run the pipeline. See **`../docs/DEV_FULL_RUN_QUEUE.md`** for failure handling, restart safety, and an **E2E verification checklist**.

**Quick pre-flight:**

```bash
cd backend && python scripts/check_redis_for_rq.py
```

**Minimal local setup**

1. Start Redis (e.g. `docker compose up redis -d` from repo root, or `docker run -p 6379:6379 redis:7-alpine`).
2. Set **`REDIS_URL`** (default `redis://localhost:6379/0`) for **both** API and worker.
3. Set **`DATABASE_URL`** to the **same** database the API uses. If Postgres is **Docker Compose** `db` service, the host maps **`localhost:5433`** → container `5432`, so use `postgresql+asyncpg://postgres:postgres@localhost:5433/contextlens` from the host (not **5432**, unless Postgres is really listening on **5432** locally).
4. From `backend/` (example matches Compose **db** on host port **5433**):

```bash
export REDIS_URL=redis://localhost:6379/0
export DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5433/contextlens
rq worker contextlens_full_run --url "$REDIS_URL"
```

**Docker Compose** (repo root): `docker compose up --build` starts **db**, **redis**, **backend** (host **http://127.0.0.1:8002** → container **:8000**), and **`worker`** (same image; internal URLs `db:5432`, `redis:6379`). After changing **`pyproject.toml`** dependencies, rebuild: **`docker compose build --no-cache backend worker`** (or **`up --build`**).

- **Retries:** RQ **`Retry(max=2)`** → **3 attempts** (initial + 2 retries), backoff **15s / 45s**; exhausted → **`on_failure`** → **`mark_run_failed_sync`** writes **`failed`** via **sync psycopg** (same DB as **`DATABASE_URL`**; avoids **`asyncio.run`** in the callback). **`GET /queue-status`** and **`POST /requeue`** may **delete** a **stale** Redis full-run lock when RQ shows **`failed`**/**`stopped`**/**`canceled`** and the run row is still **`running`**/**`failed`**.
- **503** if Redis is unreachable at enqueue time.

## Health

`GET /health` — returns `{"status": "ok"}`

## Benchmark → metrics (quickstart)

```bash
python scripts/seed_benchmark.py
python scripts/run_benchmark.py
python scripts/run_benchmark.py --eval-mode full   # needs OPENAI_API_KEY (default provider)
python scripts/generate_contextlens_metrics.py --format markdown
```

See **`../docs/BENCHMARK_WORKFLOW.md`** and **`../docs/FULL_RAG_EXAMPLE.md`**.

**Inspect a run:** `GET /api/v1/runs/{run_id}` (JSON trace for demos).
