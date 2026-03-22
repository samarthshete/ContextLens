# ContextLens — Master Project Document

## 1. Overview

ContextLens is a RAG evaluation and debugging platform.

It helps answer:
"My RAG system gave a wrong answer — where did it fail?"

**Target end-to-end flow (V1):**
query → retrieval → context → answer → evaluation → failure classification

---

## 2. Core Goal

Make RAG systems:
- observable
- debuggable
- comparable
- measurable

---

## 3. Scope

### IN SCOPE (V1)
- document upload + parsing
- chunking (fixed + recursive)
- embeddings (local)
- vector retrieval (pgvector)
- answer generation (**OpenAI** by default; optional **Anthropic**) — **implemented on benchmark/offline path** (`rag_generation`, `generation_phase`); **not exposed as a standalone HTTP “chat” API**
- full trace storage — **retrieval + optional `generation_results` + `evaluation_results`**
- evaluation — **heuristic** (`minimal_retrieval_heuristic_v1`, `evaluator_type: heuristic`) **or LLM judge** (`claude_llm_judge_v1`, `evaluator_type: llm`, `used_llm_judge=true` when judge runs)
- failure classification — **strict taxonomy** in `app/domain/failure_taxonomy.py`; persisted `failure_type` normalized to enum strings; LLM judge constrained to same set
- benchmark datasets — **idempotent seed + CLI runner** (`scripts/seed_benchmark.py`, `scripts/run_benchmark.py` with `--eval-mode heuristic|full`); **evidence-backed corpus** — `benchmark-datasets/evidence-rag-v1/` with `scripts/seed_evidence_benchmark.py`, `run_evidence_benchmark.py`, measured summaries in **`docs/benchmark-results.md`**; **`rag_systems_retrieval_engineering_v1`** — `backend/benchmark_data/rag_systems_retrieval_engineering_v1/` with `scripts/seed_rag_systems_benchmark.py`, `run_rag_systems_benchmark.py`, measured results in **`docs/benchmark_results_rag_systems_retrieval_engineering_v1.md`**
- metrics from DB — **`scripts/generate_contextlens_metrics.py` + `app/metrics/aggregate.py`** — **split by evaluator** (`avg_*_heuristic` / `avg_*_llm`; no blended score averages); **N/A vs zero** documented in generated Markdown and **`PROJECT_METRICS.md`**; **`cost_usd`** on full RAG = generation + judge estimates, **NULL** when both active-provider rates ≤ 0 or usage unknown (see **`DECISIONS.md`**)
- **config comparison from stored runs** — `GET /api/v1/runs/config-comparison` (per-bucket metrics unless `combine_evaluators=true`; per-row **`avg_faithfulness`** = SQL **`AVG`** over non-null judge rows in that bucket; **`score_comparison_buckets`** `{ heuristic, llm }` and single-bucket **`score_comparison`** with **`best_config_*` / `worst_config_*` / `*_delta_pct`** — see **`DECISIONS.md`**; faithfulness summary **omitted** on **`combine_evaluators`** merge; completeness still computed there)
- **benchmark UI** — React + Vite (`frontend/`): **SPA with client-side routing** (`react-router-dom` `BrowserRouter`; routes: `/benchmark`, `/runs`, `/queue`, `/runs/:runId`, `/documents/:documentId`, `/compare`, `/dashboard`; URL is source of truth for view selection; deep links + browser history supported); **Run** tab — **workflow intro** + **in-UI registry CRUD** (datasets / query cases / pipeline configs via existing `POST`/`PATCH`/`DELETE` APIs, preserving selections on reload where possible) + **corpus scope** block (**all indexed chunks** vs one document) + **`UploadDocumentPanel`** (`POST /documents`, list refresh, auto-select, **local** upload errors); **Recent runs** / **Queue browser** (`/queue`: merged **`GET /runs`** slices + on-demand **`queue-status`** + **Operator readout** badges from **`queueOperatorState.ts`** — queue-status JSON only; recovery hint + post-requeue list reload) / **Config comparison** / **Dashboard** — **`DashboardPanel`** calls **`GET /runs/dashboard-summary`** + **`GET /runs/dashboard-analytics`** (+ optional **`GET /runs/config-comparison`**); **Vitest** mocks API for CI; **live** check logged **2026-03-21** in **`CURRENT_STATE.md`** / **`docs/DEV_FULL_RUN_QUEUE.md` §8** (curl + Vite proxy + empty/populated DB; restart backend if **`/dashboard-analytics`** **404** on stale uvicorn); **Run detail** — **diagnosis panels** + **`RunDiffPanel`** + **retrieval hit source labels** (`document_id` from API; optional **title** from client document registry) + **`RetrievalHitsSection`** / **`retrievalSourceFormat.ts`** + trace + **`RunQueuePanel`** + **Export JSON** (current run payload); **full** runs: **202** + polling + long-run hint; **Dashboard exports** — **Export JSON** / **Export CSV** from loaded **`dashboard-summary`** + **`dashboard-analytics`** (`exportDownload.ts`, no new HTTP routes); Vitest (**199** tests); **`/compare`** shows **`scoreComparisonDisplay`** + extra table columns for **avg faith. / comp.**; **Recent runs** — **`RunsFilterBar`** (`GET /runs` server filters + labeled client **narrow** on loaded rows)

### OUT OF SCOPE
- full user auth / multi-tenant identity (optional **shared write key** for hosted demos — see **`docs/DEPLOYMENT.md`**, **`GET /api/v1/meta`**)
- billing
- multi-tenant
- plugins
- hybrid retrieval
- reranking (later)
- cloud infra

---

## 4. Frozen Stack

Backend:
- FastAPI
- SQLAlchemy (async)
- Alembic

DB:
- PostgreSQL + pgvector

Frontend:
- React + Vite + TypeScript
- Tailwind — **scaffold may exist; not part of current backend verification**

AI:
- Embeddings: all-MiniLM-L6-v2 (implemented)
- LLM (benchmark / full RAG path): **OpenAI by default** (`LLM_PROVIDER=openai`) — generation via **Responses API**, judge via **Chat Completions** + JSON mode; **optional Anthropic** (`LLM_PROVIDER=anthropic`, `CLAUDE_API_KEY`). **`require_llm_api_key_for_full_mode`** gates **`eval_mode=full`** and **`POST /requeue`** for the active provider.

---

## 5. Architecture Flow


Upload → Parse → Chunk → Embed → Store  
*(ingest path shared by API and `text_document_ingest` for scripts)*

**Benchmark path — heuristic (default):**  
seed → corpus → per (query × config): **Run** → Retrieve → `retrieval_completed` → heuristic eval → `evaluation_results` → `completed`  
*`total_latency_ms` (caller-measured) = retrieval + evaluation; `generation_latency_ms` null*

**Benchmark path — full RAG (`run_benchmark.py --eval-mode full`):**  
same through retrieval → **LLM generation** (OpenAI default) → `generation_results` row + `generation_completed` + `generation_latency_ms` → **LLM judge** → `evaluation_results` (`faithfulness`, `completeness`, `groundedness`, …, `failure_type`, `cost_usd` = summed gen+judge estimate when pricing env rates allow, else `NULL`) → `completed`  
*`total_latency_ms` = retrieval + generation + evaluation (each phase measured)*

Metrics → aggregated from stored rows only (`aggregate.py` → Markdown)

---

## 6. Data Model

IMPORTANT: use `metadata_json` not `metadata`


Tables:

- documents
- chunks
- datasets
- query_cases
- pipeline_configs
- runs
- retrieval_results
- generation_results *(1:1 with run; answer text + model + token usage)*
- evaluation_results *(includes optional `groundedness`)*

All tables are managed via Alembic migrations.

Trace tables are actively used for:
- benchmark runs
- retrieval / generation / evaluation logging
- metrics aggregation

---

## 7. Failure Types (taxonomy)

Canonical values (see `FailureType` enum): **NO_FAILURE**, **RETRIEVAL_MISS**, **RETRIEVAL_PARTIAL**, **CHUNK_FRAGMENTATION**, **CONTEXT_TRUNCATION**, **ANSWER_UNSUPPORTED**, **ANSWER_INCOMPLETE**, **MIXED_FAILURE**, **UNKNOWN**.

Persisted `failure_type` is normalized via `normalize_failure_type()`. Heuristic path uses **RETRIEVAL_MISS** when there are no retrieval rows.

---

## 8. API — Implemented (backend)

Prefix: `/api/v1`

**System**
- `GET /health` — `{ status, write_protection }` when write key configured
- `GET /api/v1/meta` — `{ write_protection, app_env }` (no secrets)
- `POST /api/v1/meta/verify-write-key` — validates `X-ContextLens-Write-Key` when write protection is enabled

**Documents**
- `POST /documents` — multipart upload; parse, chunk, embed, persist  
- `GET /documents` — list  
- `GET /documents/{document_id}` — detail  
- `DELETE /documents/{document_id}` — delete + cascade chunks  
- `GET /documents/{document_id}/chunks` — list chunks  

**Chunks**
- `GET /chunks/{chunk_id}` — single chunk  

**Retrieval**
- `POST /retrieval/search` — semantic search over chunk embeddings  

**Benchmark registry (discover IDs for UI / `POST /runs` + CRUD)**
- `GET` / `POST` / `PATCH` / **`DELETE`** `/datasets` — list, create, partial update, delete (**409** if any query cases exist)  
- `GET` / `POST` / `PATCH` / **`DELETE`** `/query-cases` — list (optional `?dataset_id=`), create, patch, delete (**409** if any runs reference the case)  
- `GET` / `POST` / `PATCH` / **`DELETE`** `/pipeline-configs` — list, create, patch, delete (**409** if any runs reference the config)  
- Successful **`DELETE`** returns **204**; missing row **404**  

**Runs**
- `POST /runs` — traced benchmark execution: body `{ query_case_id, pipeline_config_id, eval_mode?, document_id? }` (integer PKs); optional **`document_id`** scopes retrieval (same as `search_chunks` / `run_benchmark.py --document-id`). `eval_mode` is `heuristic` (default) or **`full`** (LLM generation + judge via **active `LLM_PROVIDER`** — default **OpenAI**; optional **Anthropic**; requires provider API key). **Heuristic:** synchronous **201** + `{ run_id, status, eval_mode }` (retrieval commits expose `running` / `retrieval_completed` before completion). **Full:** **202** + `{ run_id, status, eval_mode, job_id }` after persisting `running` and **enqueueing RQ** (queue `contextlens_full_run`, Redis-backed); a **separate worker** runs the pipeline (durable across API restarts; RQ retries transient failures). Poll `GET /runs/{run_id}` for progress. **503** if Redis/queue unavailable or full mode without API key. **502** mainly for heuristic synchronous failures; full-mode LLM failures after retries surface as run status **`failed`**.
- `GET /runs` — paginated list (`limit`, `offset`, `total`); filters: `dataset_id`, `pipeline_config_id`, `evaluator_type` (`heuristic` \| `llm`), `status`; sort **newest first** (`created_at`, then `id`)
- `GET /runs/dashboard-summary` — read-only **observability** aggregates for the UI **Dashboard**: **`scale`** object — **`benchmark_datasets`**, **`total_queries`**, **`total_traced_runs`**, **`configs_tested`**, **`documents_processed`**, **`chunks_indexed`** (exact **`COUNT`** / **`COUNT DISTINCT`** definitions in **`DECISIONS.md`**, aligned with **`app/metrics/aggregate.py`** except **`documents_processed`** = processed documents only); run + status + evaluator bucket counts; latency averages (non-null columns), **`retrieval_latency_p50_ms`** / **`retrieval_latency_p95_ms`** (PostgreSQL **`percentile_cont`** over persisted **`runs.retrieval_latency_ms`**, same population as the retrieval mean; **`null`** when no samples), **`avg_total_latency_ms`** plus **`end_to_end_run_latency_avg_sec`** / **`end_to_end_run_latency_p95_sec`** (same non-null **`runs.total_latency_ms`** population as the total mean; **`percentile_cont(0.95)`** for P95; seconds = ms ÷ 1000; **`null`** when no samples), **`cost`**: **`total_cost_usd`**, **`avg_cost_usd`** (mean over eval **rows** with non-null **`cost_usd`**), **`avg_cost_usd_per_llm_run`** + **`llm_runs_with_measured_cost`** (LLM-bucket only, per-run **`SUM`→`AVG`** — **`DECISIONS.md`**), **`avg_cost_usd_per_full_rag_run`** + **`full_rag_runs_with_measured_cost`** (subset with **`generation_results`**), row availability counts, failure-type counts, **recent** runs (20) with cost/failure — **`app/services/dashboard_summary.py`** + shared **`app/services/phase_latency_distribution.py`**
- `GET /runs/dashboard-analytics` — **time series** (daily run counts, latency, cost over 90 days), **latency distribution** (min/avg/median/p95/max per phase), **`end_to_end_run_latency_avg_sec`** / **`end_to_end_run_latency_p95_sec`** (same aggregates as **`latency_distribution.total`** avg/p95, in seconds), **failure analysis** (overall + per-config breakdown + recent failed runs), **config insights** (per-pipeline aggregate metrics with scores and top failure type) — **`app/services/dashboard_analytics.py`**
- `GET /runs/config-comparison` — aggregate **traced** runs (≥1 retrieval + evaluation join) per `pipeline_config_id`: counts, avg/p95 latencies (retrieval / evaluation / total), avg scores (**faithfulness** where non-null in bucket, groundedness, completeness, retrieval_relevance, context_coverage), `failure_type` counts, avg `cost_usd`. Default `evaluator_type=both` returns **`buckets.heuristic`** and **`buckets.llm`** separately plus **`score_comparison_buckets`** (cross-config best/worst **pipeline_config_id** + **delta %** per dimension — **`DECISIONS.md`**); `combine_evaluators=true` merges into one row per config (`evaluator_type=combined`) with **`score_comparison`** (completeness spread only; faithfulness fields **null**); or set `evaluator_type=heuristic|llm` for a single bucket with **`score_comparison`** only.
- `GET /runs/{run_id}` — full trace (**`run_id` is numeric only** — Starlette `{run_id:int}` so static paths like `/runs/dashboard-summary` are never parsed as an id); query, pipeline config, retrieval hits (rank, score, chunk text), optional generation, evaluation scores, timings, cost, resolved **evaluator_type** (`heuristic` | `llm` | `none`)
- `GET /runs/{run_id}/queue-status` — same numeric `run_id`; read-only **Redis lock** + best-effort **RQ job** scan for **full** runs (**200**); **stale-lock** reconcile when RQ shows terminal failed job + run still mid-flight; **heuristic** runs return `pipeline=heuristic` without calling Redis; **404** / **503** — **`docs/DEV_FULL_RUN_QUEUE.md`**
- `POST /runs/{run_id}/requeue` — same numeric `run_id`; re-submit an **eligible** full-mode run to RQ (**202** + `run_id`, `status`, `job_id`); stale-lock reconcile before lock **409**; **404** / **409** / **503** — **`docs/DEV_FULL_RUN_QUEUE.md`**

**Full mode operations** — Redis + RQ worker, retries, restart expectations, and a dev **verification checklist**: **`docs/DEV_FULL_RUN_QUEUE.md`**. Pre-flight: `cd backend && python scripts/check_redis_for_rq.py`.

**Not implemented**
- Evaluation **write** endpoints (other than run lifecycle via `POST /runs` / requeue)  

---

## 9. Phases (roadmap)

| Phase | Topic | Status |
|-------|--------|--------|
| 1 | Foundation (FastAPI, DB, Docker, Alembic) | Done |
| 2 | Ingestion + chunking | Done |
| 3 | Embeddings + retrieval | Done |
| **4** | **Tracing + metrics + benchmark + full RAG eval + benchmark UI + queued full runs** | **In progress** (heuristic **`POST /runs`** synchronous; full mode **RQ + Redis**; no standalone HTTP “chat” generation route) |
| 5 | **Client-side routing** | **Done** — `react-router-dom` BrowserRouter; URL-driven view selection; `/runs/:runId` deep links |
| 6 | **Dashboard analytics** | **Done** — `GET /runs/dashboard-analytics` + UI + tests; **live** curl + Vite proxy + empty/populated DB validated **2026-03-21** (see **`CURRENT_STATE.md`**, **`DEV_FULL_RUN_QUEUE.md` §8**) |
| 7+ | Queue admin UI / deeper features | Later |

---

## 10. Rules

- Backend correctness > frontend  
- Do not expand scope without updating this doc  
- Do not add infra early  
- Keep system inspectable  
- Target: always store trace for benchmark runs  

---

## 11. Backend status today (verified)

### Implemented
- Document ingestion pipeline (API delegates to `app/services/text_document_ingest.py`)
- Chunking (fixed + recursive)
- Embeddings (MiniLM, 384-dim)
- pgvector storage + HNSW index
- Semantic retrieval API
- Retrieval benchmark execution (`execute_retrieval_benchmark_run`) + persistence
- **RAG generation** (`rag_generation` + `execute_generation_for_run`) → `generation_results`
- **LLM judge evaluation** (`llm_judge_evaluation` + `execute_llm_judge_and_complete_run`)
- Evaluation row persistence (`evaluation_persistence` with `prerequisite_status`: `retrieval_completed` vs `generation_completed`)
- **Heuristic evaluation** (`minimal_retrieval_heuristic_v1`) — `evaluator_type: heuristic`
- **Failure taxonomy** (`app/domain/failure_taxonomy.py`)
- Benchmark seed + runner (`--eval-mode heuristic|full`)
- Run lifecycle: `pending` → `running` → `retrieval_completed` → *(optional)* `generation_completed` → `completed` (or **`failed`** on errors / exhausted RQ retries)
- Metrics aggregation + Markdown script (**heuristic vs LLM sections**; `groundedness` per bucket)
- **Benchmark registry API** — `GET` + **`POST`/`PATCH`/`DELETE`** on `/api/v1/datasets`, `/api/v1/query-cases`, `/api/v1/pipeline-configs` — `*_list.py`, `*_write.py`, `*_delete.py`, `schemas/*_read.py`, `schemas/*_write.py`
- **Runs API** — handlers in `api/runs.py`; `POST /api/v1/runs` (optional `document_id`; `run_create.py`), `GET /api/v1/runs` (`run_list.py`), `GET /api/v1/runs/dashboard-summary` (`services/dashboard_summary.py`), `GET /api/v1/runs/dashboard-analytics` (`services/dashboard_analytics.py`), `GET /api/v1/runs/config-comparison` (`config_comparison.py`); **`{id:int}`** on `GET /api/v1/runs/{id}` (`run_detail.py`), `GET …/queue-status` (`services/run_queue_status.py`), `POST …/requeue` (`services/run_requeue.py`) so static `/runs/*` slugs are not parsed as ids
- **LLM judge** — `llm_judge_evaluation.py` + `llm_judge_parse.py`: **`judge_prompt_version`** (`claude_llm_judge_v2`) on every judge row; **`judge_parse_ok`** / **`judge_parse_warnings`**; **one automatic retry** when the first response is structurally bad (`judge_initial_parse_ok`, `judge_retry_attempted`, `judge_retry_succeeded`); token totals sum both judge calls when retried; observability: `judge_score_clamping_occurred`, `judge_scores_raw`, `judge_raw_failure_type`, `judge_parse_warning_count`

### Not implemented / gaps
- **`eval_mode=heuristic`:** `POST /runs` remains **synchronous** (inline). **`eval_mode=full`:** **durable queue** (RQ + Redis + worker); not “async” in the sense of a second public job-status API — clients use **`GET /runs/{id}`** and optional **`job_id`** on **202**.
- **Queue ops:** **HTTP re-enqueue** + **`GET /queue-status`** on **Run detail** **`RunQueuePanel`** and on **`/queue`** **Queue browser** (per-row refresh; same eligibility rules); **RQ `on_failure`** marks runs **`failed`** via sync **psycopg** (no invalid **`asyncio.run`** in callbacks); **stale Redis lock** reconcile when RQ job is **`failed`**/**`stopped`**/**`canceled`** and the run is still **`running`**/**`failed`** (worker killed without releasing lock). Full **RQ job browser** / bulk admin still out of scope. **Phase 4 closure:** each **target** environment still needs the **human** checklist in **`docs/DEV_FULL_RUN_QUEUE.md` §5 + §8 (validation log)**; repo also ships **§5b** automated queue API tests + Compose config validation.
- **Auth:** no per-user login; optional **`CONTEXTLENS_WRITE_KEY`** + header **`X-ContextLens-Write-Key`** gates non-GET `/api/v1` when set; SPA unlock stores key in **sessionStorage** (`WriteKeyBanner`). **`APP_ENV=production`** requires non-empty write key and disallows wildcard CORS — see **`docs/DEPLOYMENT.md`**
- **Deploy prep:** root **`render.yaml`** (Render Blueprint: Postgres 16 + Key Value + Docker web + worker); **`backend/Dockerfile`** includes **`alembic/`** + **`scripts/rq_worker.sh`** for `preDeployCommand` / worker parity; **`DATABASE_URL`** `postgresql://` from providers is normalized to **`postgresql+asyncpg://`** in **`app.config`**
- Pricing defaults are **config estimates**; set **`OPENAI_*`** or **`ANTHROPIC_*`** per-million rates to `0` (per active **`LLM_PROVIDER`**) to omit `cost_usd`

### Automated checks (current repo)
- **Backend:** **168** `pytest` tests under `backend/tests/` (includes **`test_dashboard_summary_api.py`** cost-per-run semantics + **`test_config_comparison_scores.py`** — pure unit tests for **`build_config_score_comparison`** + `no_database_cleanup`; **`test_runs_api`** config-comparison JSON shape; **`test_phase_latency_distribution.py`** — retrieval + **`total_latency_ms`** aggregates, **`test_dashboard_summary_api.py`** — dashboard **`scale`** counts + traced-run delta, **`test_database_url_normalization.py`**, write-key / **`GET /api/v1/meta`** / production config validation, OpenAI/Anthropic provider keys, cost estimation, run requeue, **queue-status**, **`GET /runs/dashboard-summary`**, **`GET /runs/dashboard-analytics`**, routing regression, **interrupted full-run** failure callback + stale-lock tests, registry + judge + metrics coverage, **evidence-rag-v1** + **`rag_systems_retrieval_engineering_v1`** dataset file grounding tests, **`no_database_cleanup`** for file-only tests). **`conftest.py`** substitutes **deterministic fake embeddings** for `sentence-transformers` so upload/retrieval tests pass **offline** without downloading MiniLM; production code still uses the real model. **Docker:** **`backend/Dockerfile`** runs **`import openai`** after **`pip install`** so images fail fast if dependencies are missing; rebuild **`backend`/`worker`** after **`pyproject.toml`** changes (**`psycopg`** ships for RQ **`mark_run_failed_sync`**). **After changing `app/api/*.py`, restart `uvicorn`** (or **`docker compose restart backend`**) so the running process picks up route changes. **Ops triage:** **`dashboard-summary` 200** + **`dashboard-analytics` 404** ⇒ **stale process**, not a missing implementation — restart **backend** first.
- **Frontend:** **199** Vitest tests — includes **`scoreComparisonFormat.test.ts`**, **`configComparisonMock`** / dashboard LLM score-spread assertion, **`queueOperatorState`** (operator queue badges + tests), **`exportDownload`** (run + dashboard export helpers), **`dashboardAnalyticsFormat`** (chart/stack helpers), **`dashboardFormat`** (**`formatLatencySec`**), **`DashboardPanel`** ( **`dashboard-system-scale`** ), **`retrievalSourceFormat`**, **`RetrievalHitsSection`** + **`DocumentDetailPanel`** (`/documents/:id`), **`runDiff`**, **`runDiagnosis`**, **`runsListQuery`** / **`RunsFilterBar`** / **`runsListPage`**, **`queueBrowserLoad`** / **`QueueBrowserPanel`**, **`runTimeline`**, **`PhaseTimeline`**, routing; **2026-03-21** live session: real **200** JSON via **curl** + **Vite proxy** (headed browser not automated). **E2E:** **14** Playwright tests — **`e2e/run-detail.spec.ts`** (11) + **`e2e/runs-list.spec.ts`** (1) + **`e2e/queue-browser.spec.ts`** (1) + **`e2e/dashboard.spec.ts`** (1); `page.route()` API mocking; `npx playwright install` then `npx playwright test`.

## Metrics

All reported aggregate metrics are derived from stored rows. **Score and failure-type averages are not mixed across evaluators** — use `_heuristic` vs `_llm` suffix keys from `aggregate.py` (see `docs/METRICS_INSTRUMENTATION.md` and generated Markdown “Semantics” section). **not available** when a slice has no rows.

Metrics are generated using: `backend/scripts/generate_contextlens_metrics.py`
