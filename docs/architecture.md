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

**Frontend** is a single-page app with client-side routing (`react-router-dom`). Routes: `/benchmark`, `/runs`, `/runs/:runId`, `/queue`, `/compare`, `/dashboard`.

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
| `runs` | One execution per query × config; stores phase latencies |
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
| `GET /runs/dashboard-summary` | Aggregate stats: counts, latency, cost, failures |
| `GET /runs/dashboard-analytics` | Time series, latency distribution, failure breakdown, config insights |
| `GET /runs/config-comparison` | Per-config aggregates with evaluator bucketing |
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

9 types: `NO_FAILURE`, `RETRIEVAL_MISS`, `RETRIEVAL_PARTIAL`, `CHUNK_FRAGMENTATION`, `CONTEXT_TRUNCATION`, `ANSWER_UNSUPPORTED`, `ANSWER_INCOMPLETE`, `MIXED_FAILURE`, `UNKNOWN`.

All failure types are normalized via `normalize_failure_type()` before persistence.

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

- **178 pytest tests** — fully offline via deterministic fake embeddings in `conftest.py`
- **199 Vitest tests** — component + logic tests with mocked API
- **14 Playwright E2E tests** — `page.route()` API mocking, no backend required
