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

9 canonical types defined in `app/domain/failure_taxonomy.py`. All persisted `failure_type` values pass through `normalize_failure_type()` — unknown labels become `UNKNOWN`.

## Client-Side Diagnosis

Diagnosis, run diff, phase timeline, and retrieval source labels are computed in TypeScript from the existing run trace. No new backend endpoints. This keeps the logic deterministic, testable in isolation, and avoids unnecessary API contracts.

## Full-Mode Runs

Enqueued via RQ, executed by a worker process, backed by Redis. Jobs survive API restarts but not Redis data loss. RQ retries transient failures (3 attempts with backoff). `on_failure` uses sync psycopg (not asyncio) to mark runs as failed.

## Write Protection

Optional `CONTEXTLENS_WRITE_KEY` header gates non-GET requests. `APP_ENV=production` requires a non-empty key and disallows wildcard CORS. Not a substitute for auth — just a demo-safe guard rail.

## Cost Aggregation

Dashboard cost metrics use per-run subqueries (`SUM(cost_usd) GROUP BY run_id`) before averaging into daily or per-config buckets. This prevents inflation from join cardinality, even if the schema ever allows multiple evaluation rows per run.

## Config Comparison

Cross-config score comparison (`best_config_*`, `worst_config_*`, `delta_pct`) is computed within a single evaluator bucket. When `combine_evaluators=true`, faithfulness spread is omitted (NULL) because blending heuristic NULLs with LLM scores would be misleading.
