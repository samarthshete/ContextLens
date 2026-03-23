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

**System vs model failures:** `status_counts.failed` reflects run **status** (pipeline did not complete). `model_failures` on the same summary counts **evaluation** rows (organic scope) whose `failure_type` is set and not `NO_FAILURE`. UI copy distinguishes these. **Latency** panels emphasize P50/P95 over the mean and state directional / cold-start caveats; dashboard-summary exposes **`total_latency_p50_ms`** / **`end_to_end_run_latency_p50_sec`**. **LLM dashboard UI:** `llm_runs` **&lt; 3** → hide LLM cost, LLM compare bucket, and LLM config-insights table (sparse warning only); **3–9** → illustrative limited-evidence copy; **`repeated_sampling_note`** on summary is shown under run-count stats.

## Config Comparison

Cross-config score comparison (`best_config_*`, `worst_config_*`, `delta_pct`) is computed within a single evaluator bucket. Heuristic and LLM buckets are not merged in the API. **`traced_runs`** and **`unique_query_count`** use a **`run_base`** slice (scoped runs with ≥1 **`retrieval_results`** row), not “only rows with an evaluation in this bucket,” so run volume matches dashboard-style “has retrieval” scope; score aggregates still require eval rows in the bucket. Optional query params `dataset_id`, `min_traced_runs`, and `strict_comparison` enforce comparable samples. Rows expose `stddev_samp_*` for key scores where measurable (PostgreSQL `STDDEV_SAMP`; null when n&lt;2).

### Effective Sample Size and Confidence Tiers

`effective_sample_size` = `min(unique_query_count across all compared configs)`, **not** raw traced run count. When the same 6 queries are each run 4× across 2 configs, traced runs = 24 but effective_sample_size = 6. Confidence is based on this smaller number:

| effective_sample_size | comparison_confidence |
|-----------------------|-----------------------|
| < 8                   | LOW                   |
| 8–14                  | MEDIUM                |
| ≥ 15                  | HIGH                  |

`comparison_statistically_reliable` = `true` only when `effective_sample_size ≥ 10`. These fields are always returned in the API response and surfaced as banners in the comparison panel — treat score deltas as directional when confidence is LOW or MEDIUM.

### Repeated Sampling Note

When total traced runs > unique queries across compared configs, the API returns a `repeated_sampling_note` (e.g. "53 runs across 6 unique queries (repeated sampling; results are directional, not broad generalization)"). The UI surfaces this note above comparison results so readers understand the query-reuse pattern.

## Latency Honesty

All latency figures in the dashboard and benchmark results are from **local runs** and are **directional only**. Cold-start, OS scheduler jitter, and model-cache warm-up can dominate early runs and inflate averages significantly. The UI:

- **Summary latency card:** order **median (P50) → P95 → mean** (mean visually de-emphasized); end-to-end includes **`total_latency_p50_ms`** / **`end_to_end_run_latency_p50_sec`** from the same population as total mean/P95.
- **Latency distribution panel:** **skew warning** (`role="alert"`) + fixed **median vs average** sentence when any phase has samples; per phase with **&lt;5** non-null timings → only *Insufficient samples for distribution (N runs)* (no percentile table/bars for that phase); **≥5** → bars + table with median before P95 before mean.
- **Badges** (when phase `count > 0`): **Low sample — not reliable** if count **&lt; 20**; **High variance (skewed distribution)** if **P95/median > 10** (constants in `frontend/src/benchmark/dashboardConstants.ts`).

Do not quote any latency number from a local run as a production-grade performance claim or SLA.
