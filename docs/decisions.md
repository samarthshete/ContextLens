# Design Decisions

Key architectural and design choices, with rationale.

---

## Identity

ContextLens is a RAG debugging and evaluation tool. It is not a chatbot. There is no public generation endpoint — LLM calls exist only on the benchmark pipeline.

## Stack

- **FastAPI** + async SQLAlchemy + Alembic (sole schema source)
- **PostgreSQL + pgvector** — no external vector DB
- **React + Vite + TypeScript** — no Next.js
- **Redis + RQ** for durable full-mode runs (not FastAPI BackgroundTasks)

## Embeddings

`all-MiniLM-L6-v2` (384-dim, L2-normalized). Local model, no API dependency. Tests use deterministic fake vectors so CI runs fully offline.

## Retrieval

Vector-only search via pgvector cosine operator (`<=>`). HNSW index with `vector_cosine_ops`. Scores are `1 - cosine_distance`. No hybrid retrieval or reranking in V1.

## Evaluation: Two Modes, Never Blended

**Heuristic:** retrieval relevance + context coverage. No LLM. `cost_usd` = NULL. `faithfulness` = NULL.

**LLM Judge:** faithfulness, completeness, groundedness. Requires API key. `cost_usd` = generation + judge estimate.

Score averages are always computed per evaluator bucket. Heuristic and LLM scores are never mixed in aggregations, dashboards, or comparisons.

## NULL vs Zero

NULL means "not measured." Zero means "measured as zero." This distinction is enforced everywhere:
- `cost_usd` is NULL when pricing is disabled or usage is unknown — never a fake zero
- Score averages with no contributing rows are NULL, not zero
- Dashboard and metrics display "N/A" for NULL, "$0.00" for true zero

## Failure Taxonomy

10 canonical types in `app/domain/failure_taxonomy.py` (including `CONTEXT_INSUFFICIENT` for weak query–context overlap under heuristic rules). All persisted `failure_type` values pass through `normalize_failure_type()` — unknown labels become `UNKNOWN`.

## Client-Side Diagnosis

Diagnosis, run diff, phase timeline, and retrieval source labels are computed in TypeScript from the existing run trace. No new backend endpoints. This keeps the logic deterministic, testable in isolation, and avoids unnecessary API contracts.

## Full-Mode Runs

Enqueued via RQ, executed by a worker process, backed by Redis. Jobs survive API restarts but not Redis data loss. RQ retries transient failures (3 attempts with backoff). `on_failure` uses sync psycopg (not asyncio) to mark runs as failed.

## Write Protection

Optional `CONTEXTLENS_WRITE_KEY` header gates non-GET requests. `APP_ENV=production` requires a non-empty key and disallows wildcard CORS. Not a substitute for auth — just a demo-safe guard rail.

## Cost Aggregation

Dashboard cost metrics use per-run subqueries (`SUM(cost_usd) GROUP BY run_id`) before averaging into daily or per-config buckets. This prevents inflation from join cardinality, even if the schema ever allows multiple evaluation rows per run.

## Dashboard aggregates vs run list

`GET /runs/dashboard-summary`, `GET /runs/dashboard-analytics`, `GET /runs/config-comparison`, and generated metrics from `aggregate.py` exclude runs tagged with `benchmark_realism` in `runs.metadata_json` (batch stress / realism experiments). The run list and run detail endpoints still return every stored run.

## Config Comparison

Cross-config score comparison (`best_config_*`, `worst_config_*`, `delta_pct`) is computed within a single evaluator bucket. Heuristic and LLM buckets are not merged in the API. Optional query params `dataset_id`, `min_traced_runs`, and `strict_comparison` enforce comparable samples (same dataset slice, minimum runs per config, identical query-case coverage when strict). Rows expose `stddev_samp_*` for key scores where measurable (PostgreSQL `STDDEV_SAMP`; null when n&lt;2).
