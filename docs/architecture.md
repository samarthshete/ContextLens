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

---

## Data Model

| Table | Purpose |
|-------|---------|
| `documents` | Uploaded files (PDF, TXT, Markdown) |
| `chunks` | Text segments with 384-dim embeddings |
| `datasets` | Benchmark dataset registry |
| `query_cases` | Queries with optional expected answers |
| `pipeline_configs` | Frozen retrieval parameters (top-k, chunk strategy) |
| `runs` | One execution per query × config; phase latencies; optional `metadata_json` (batch / experiment tags) |
| `retrieval_results` | Per-chunk scores and ranks for each run |
| `generation_results` | LLM answer text, model, token usage (1:1 with run) |
| `evaluation_results` | Scores, failure type, cost, judge metadata |

All tables managed via Alembic migrations. No `create_all` in production.

---

## API Surface

Prefix: `/api/v1`

| Endpoint | Purpose |
|----------|---------|
| `POST /runs` | Execute a benchmark run (heuristic: 201 sync; full: 202 + RQ job) |
| `GET /runs` | Paginated list with filters (status, evaluator, dataset, config) |
| `GET /runs/{id}` | Full trace: retrieval hits, generation, evaluation, timings |
| `GET /runs/dashboard-summary` | Aggregate stats: counts (`status` vs `model_failures` on eval rows), latency (retrieval P50/P95 + mean; total mean + **`total_latency_p50_ms`** + **`end_to_end_run_latency_p50_sec`** / avg / P95 seconds — same SQL population as `phase_latency_distribution` for `total_latency_ms`), `repeated_sampling_note`, cost, `failure_type_counts`. Optional `dataset_id` scopes run-derived fields; **404** if missing. Latency is directional (local cold-start skew), not a benchmark score. |
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

The run detail view computes diagnosis, diff, timeline, and source labels entirely in TypeScript from the existing `GET /runs/{id}` payload. No additional API calls. This is an intentional architectural decision — the trace is already complete.

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

## Testing

- **215 pytest tests** — fully offline via deterministic fake embeddings in `conftest.py`
- **227 Vitest tests** — component + logic tests with mocked API
- **14 Playwright E2E tests** — `page.route()` API mocking, no backend required
