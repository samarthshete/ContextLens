# Architecture

## Overview

ContextLens is a single-tenant RAG evaluation platform. It instruments every stage of a retrieval-augmented generation pipeline, stores the full trace, and provides tools to diagnose, compare, and measure runs.

There is no public "ask a question" endpoint. Generation exists only on the benchmark path.

---

## System Layout

```
Browser  →  React SPA (Vite)
               ↓  /api proxy
            FastAPI (async, Python)
               ↓
    ┌──────────┼──────────────┐
    │          │              │
 PostgreSQL  Redis + RQ    OpenAI / Anthropic
 + pgvector  (full runs)   (generation + judge)
```

**Frontend** is a single-page app with client-side routing (`react-router-dom`). Routes include `/benchmark`, `/runs`, `/runs/:runId`, `/documents/:documentId`, `/queue`, `/compare`, `/dashboard`.

**Backend** is a FastAPI application with async SQLAlchemy. All benchmark runs produce traced database rows.

**Worker** is a separate process running `rq worker`. It handles full-mode runs (generation + LLM judge) so they survive API restarts.

---

## Data Flow

### Ingest

```
Upload → Parse → Chunk (fixed or recursive) → Embed (MiniLM 384-dim) → pgvector
```

### Benchmark — Heuristic

```
Query × Config → Retrieve top-k → Heuristic eval → Trace stored → completed
```

Synchronous. No LLM calls. No API key required.

### Benchmark — Full RAG

```
Query × Config → Retrieve → LLM Generate → LLM Judge → Trace stored → completed
```

Enqueued via Redis + RQ. Durable across API restarts.

### Benchmark — Full RAG (hybrid judge gate)

Same enqueue path as full RAG, but runs created with `evaluator_execution_mode=hybrid` (`eval_mode=full_hybrid` on `POST /runs` or batch `-e llm_hybrid`). After generation, if persisted retrieval scores pass fixed thresholds (`app/services/minimal_retrieval_evaluation.py`), the **LLM judge is skipped** and heuristic-style scores (plus lexical “faithfulness” from generated text vs retrieved context) are written to `evaluation_results` with `used_llm_judge=false`. **`runs.trace_instrumentation_json`** records judge calls attempted / skipped / used for aggregation.

---

## Data Model

| Table | Purpose |
|-------|---------|
| `documents` | Uploaded files (PDF, TXT, Markdown) |
| `chunks` | Text segments with 384-dim embeddings |
| `datasets` | Benchmark dataset registry |
| `query_cases` | Queries with optional expected answers |
| `pipeline_configs` | Frozen retrieval parameters (top-k, chunk strategy) |
| `runs` | One execution per query × config; phase latencies; optional `metadata_json` (batch / experiment tags); optional **`trace_instrumentation_json`** (evaluator mode + LLM judge counters) |
| `retrieval_results` | Per-chunk scores and ranks for each run |
| `generation_results` | LLM answer text, model, token usage (1:1 with run) |
| `evaluation_results` | Scores, failure type, cost, judge metadata |
| `diagnosis_timing_sessions` | Optional timed manual vs assisted diagnosis attempts on a run (`started_at`, `first_meaningful_insight_at`, `completed_at`; `synthetic` excluded from dashboard evidence) |

All tables managed via Alembic migrations. No `create_all` in production.

---

## API Surface

Prefix: `/api/v1`

| Endpoint | Purpose |
|----------|---------|
| `POST /runs` | Execute a benchmark run (heuristic: 201 sync; **full** / **full_hybrid**: 202 + RQ job) |
| `GET /runs` | Paginated list with filters (status, evaluator, dataset, config) |
| `GET /runs/{id}` | Full trace: retrieval hits, generation, evaluation, timings, optional `trace_instrumentation_json` |
| `GET/POST /runs/{id}/diagnosis-timing-sessions` | List / start diagnosis timing sessions |
| `PATCH /runs/{id}/diagnosis-timing-sessions/{session_id}` | Update insight / completion timestamps |
| `GET /runs/dashboard-summary` | Aggregate stats: counts (`status` vs `model_failures` on eval rows), latency (retrieval P50/P95 + mean; total mean + **`total_latency_p50_ms`** + **`end_to_end_run_latency_p50_sec`** / avg / P95 seconds — same SQL population as `phase_latency_distribution` for `total_latency_ms`), `repeated_sampling_note`, **`scale.unique_query_cases_with_runs`**, **`diagnosis_timing`** (tiered evidence from non-synthetic sessions), **`llm_reduction`** (matched workloads via batch metadata + instrumentation), cost, `failure_type_counts`. Optional `dataset_id` scopes run-derived fields; **404** if missing. Latency is directional (local cold-start skew), not a benchmark score. |
| `GET /runs/dashboard-analytics` | Time series, latency distribution (per-phase min/max/avg/median/p95), failure breakdown, config insights. Same optional `dataset_id` and **404** as dashboard-summary. |
| `GET /runs/config-comparison` | Per-config aggregates with heuristic/LLM bucketing. **`traced_runs`** / **`unique_query_count`** count scoped runs with ≥1 retrieval row (`run_base` CTE), independent of whether an eval row exists in that bucket; score/latency averages join eval where applicable. Returns **`comparison_confidence`**, **`effective_sample_size`** (min distinct `query_case_id` across configs), **`comparison_statistically_reliable`** (≥10 unique queries vs `recommended_min_unique_queries_for_valid_comparison`). |
| `GET /runs/{id}/queue-status` | Redis lock + RQ job state for full runs |
| `POST /runs/{id}/requeue` | Re-submit eligible failed full runs |
| `POST /documents` | Upload, parse, chunk, embed in one request |
| `GET/POST/PATCH/DELETE` on registry | CRUD for datasets, query cases, pipeline configs |

---

## Evaluation

Two evaluator modes, never blended in aggregations:

**Heuristic** — retrieval relevance and context coverage from cosine similarity. No LLM calls. `cost_usd` is NULL.

**LLM Judge** — faithfulness, completeness, groundedness via OpenAI (default) or Anthropic. Includes parse retry, structured metadata, and cost tracking.

### Failure Taxonomy

10 types in `app/domain/failure_taxonomy.py`: `NO_FAILURE`, `RETRIEVAL_MISS`, `RETRIEVAL_PARTIAL`, `CHUNK_FRAGMENTATION`, `CONTEXT_INSUFFICIENT`, `CONTEXT_TRUNCATION`, `ANSWER_UNSUPPORTED`, `ANSWER_INCOMPLETE`, `MIXED_FAILURE`, `UNKNOWN`.

All failure types are normalized via `normalize_failure_type()` before persistence.

**Dashboard semantics:** taxonomy values on `evaluation_results.failure_type` are **model-/evaluation-level** labels. **`runs.status = failed`** is a separate **system** (pipeline) outcome. The summary exposes both: status-derived **failed** count (labeled *system failures* in the UI) and **`model_failures`** (count of evaluation rows where `failure_type` is set and not `NO_FAILURE`, same organic run scope as other summary aggregates). **`scale.total_traced_runs`** counts scoped runs with an **`evaluation_results`** row only (differs from `aggregate.py` **`total_traced_runs`**, which also requires **`retrieval_results`**). **`scale.configs_tested`** is **`COUNT(DISTINCT pipeline_config_id)`** on scoped runs. **`GET /runs/config-comparison`** uses **`traced_runs`** = scoped runs with retrieval (see service SQL); `aggregate.py` “traced” = retrieval + evaluation.

---

## Client-Side Diagnosis

The run detail view computes diagnosis, diff, timeline, and source labels in TypeScript from `GET /runs/{id}`. **Diagnosis timing experiments** add small **write** endpoints (sessions) so median durations can be aggregated honestly on the dashboard; the assisted vs manual **UX gate** (hiding diagnosis widgets in “manual baseline” mode) remains client-side.

### Diagnosis experiment design (balanced timing study)

Pure logic in `app/services/diagnosis_experiment_design.py` (no DB):

1. **Buckets** — map `evaluation_results.failure_type` into four study buckets (retrieval-related, generation-incomplete, mixed/ambiguous, easy control / NO_FAILURE). Unknown labels fall into **mixed_ambiguous**.
2. **Scoring** — deterministic ranking: base +40 for non–easy-control vs **NO_FAILURE penalty** (−50 default); **difficulty bonus** from inverted eval scores; **repeat-query penalty** for second+ runs whose query text matches after normalise (strip, lower, collapse whitespace) via MD5 fingerprint; **penalty** for existing non-synthetic diagnosis sessions on the same run. Sort **(−score, −run_id)** for stable ties.
3. **Plan** — `build_experiment_plan` fills **10 manual + 10 assisted** slots with per-bucket targets **4 / 3 / 2 / 1** (retrieval / generation / mixed / easy). Greedy assignment per bucket avoids duplicate `query_case_id` across groups when possible. Emits **warnings** when a bucket has fewer than `2 × target` candidates or total slots &lt; 20.
4. **Export** — `plan_to_export_rows` uses stable keys `EXPORT_PLAN_ROW_KEYS` for CSV/JSON.

`scripts/list_diagnosis_candidates.py` loads completed runs with evaluations (optional `--dataset-id`), scores them, and prints **candidates**, **buckets**, or **plan**; `--export-plan` writes CSV/JSON.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI, SQLAlchemy (async), Alembic |
| Frontend | React 18, TypeScript, Vite |
| Database | PostgreSQL 16 + pgvector (HNSW cosine index) |
| Queue | Redis + RQ |
| Embeddings | sentence-transformers `all-MiniLM-L6-v2` (384-dim, local) |
| LLM | OpenAI (default) or Anthropic (optional) |

---

## Evidence Orchestration Scripts

| Script | Purpose |
|--------|---------|
| `scripts/run_scale_evidence_pipeline.py` | One-command pipeline: seed 52-query benchmark → execute 208 traced runs (52 queries × 2 configs × 2 reps) → verify dashboard counts. Supports `--force-recreate`, `--reps N`, `--skip-execute`, `--strict`. |
| `scripts/run_llm_reduction_evidence.py` | Matched LLM-judge reduction workload automation: creates N workload UUIDs, runs both `llm_only` and `hybrid` arms, queries `build_llm_reduction_evidence()` for tier + reduction %. Requires API key. `--dry-run` supported. |
| `scripts/list_diagnosis_candidates.py` | Fetches candidate runs → `score_candidates` → optional `build_experiment_plan`. Views: `candidates` (ranked), `buckets` (pools vs 2×targets), `plan` (20 slots + warnings). `--export-plan` (CSV/JSON), `--export-sessions` (completed sessions + evidence tier summary). |

---

## Testing

- **pytest** — backend suite, **290** tests (PostgreSQL in dev/CI; deterministic fake embeddings in `conftest.py`; includes `test_benchmark_scale_seed` 11 tests, `test_evidence_gating` 16 tests, `test_diagnosis_experiment_design` 47 tests)
- **227 Vitest tests** — component + logic tests with mocked API
- **14 Playwright E2E tests** — `page.route()` API mocking, no backend required
