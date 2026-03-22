# DECISIONS

## Identity
- ContextLens = RAG debugging tool  
- NOT a chatbot product  

## Backend
- FastAPI  
- SQLAlchemy async  
- Alembic — **sole source of DB schema** (no `create_all` in production path; `init_db()` connectivity check only)  

## Database
- PostgreSQL + pgvector  
- No external vector DB  

## Frontend
- React + Vite  
- No Next.js  
- **Run detail diagnosis (UI):** beginner-oriented **retrieval / context / generation+judge / summary** panels on **`/runs/:runId`** are **purely client-side** over the existing **`GET /api/v1/runs/{id}`** payload (`retrieval_hits`, `generation`, `evaluation` + `metadata_json`). The **Generation & judge** panel includes a readable **evaluation score grid** (same numeric fields as the API) plus parse/retry badges from metadata. **Summary + context heuristics** (thresholds, failure-taxonomy lines, sparse recall vs `top_k`, overlap detection, single-document concentration in retrieval) stay **deterministic and explainable** in `runDiagnosis.ts` — no new fields on the response. **Run diff v1:** **`RunDiffPanel`** loads a **second** run by ID with the **same** endpoint and compares deterministically in the browser (`runDiff.ts`); no dedicated diff API. **Retrieval source v1:** each hit shows **`document_id`** from the payload; **titles** are joined in the UI from the benchmark **document list** when the registry has been loaded — not extra fields on the run-detail response. **Recent runs list (`/runs`):** server filters mirror **`GET /api/v1/runs`** query params (`status`, `evaluator_type`, `dataset_id`, `pipeline_config_id`); **narrow visible rows** is client-side on **loaded** results only — not a dedicated search API. **Queue browser (`/queue`):** merged run rows from several **`GET /runs?status=…`** calls (capped); **`GET /runs/{id}/queue-status`** only on **explicit per-row refresh** (no list-wide polling); **`POST /requeue`** only when the same eligibility rules as run-detail **`RunQueuePanel`** apply — complements that panel, does not replace it. No new persistence; copy is **explanatory**, not authoritative ground truth.

## Models (AI)
- **Embeddings (implemented):** all-MiniLM-L6-v2, **384 dimensions**, L2-normalized at encode time  
- **LLM (implemented, benchmark path):** Anthropic **Messages API** via `anthropic` SDK — generation model `generation_model_name`, judge `evaluation_model_name`; requires `claude_api_key` for live calls. **Not** a user-facing chat route yet.  

## Retrieval
- Vector search only (no hybrid)  
- **pgvector** cosine operator `<=>` via SQLAlchemy comparator  
- **HNSW** index with `vector_cosine_ops`  
- **API score:** `1 − cosine_distance` → cosine similarity for normalized vectors  
- No reranking in V1 scope  

## Chunking
- Fixed + recursive only (no other strategies in scope for now)  

## Processing
- **Full benchmark runs (`eval_mode=full`):** **RQ + Redis** — durable jobs, worker process separate from the API; **not** FastAPI `BackgroundTasks` for that path.  
- Other lightweight follow-up work may still use `BackgroundTasks` if needed (none required today).  

## Transactions
- **`get_db()`** yields a session and closes it — **does not** commit or roll back  
- **Write routes/services** call `await session.commit()` explicitly  
- Do not mix auto-commit inside `get_db()` with manual commits  

## Upload pipeline (implemented order)
Shared implementation: `app/services/text_document_ingest.py` (API `POST /documents` calls `ingest_text_file` after saving upload).

1. Save file to `upload_dir`  
2. Create `document` row (`processing`)  
3. Parse → chunk → **batch embed**  
4. Insert chunks with embeddings  
5. Update document `raw_text`, `status = processed`  
6. Single commit for success path; on failure set `failed` and commit (no partial chunks)  

## Retrieval / search errors
- Embedding model load failures → **503** on search (service unavailable), not fabricated scores  

## Scope
- Single user  
- No auth  
- No billing  
- No plugins  
- No agents  

## Evaluation
- **Two evaluator kinds** (discriminated in `metadata_json.evaluator_type`):
  - **heuristic:** `minimal_retrieval_heuristic_v1` — no LLM; `used_llm_judge=false`; `faithfulness` null; `cost_usd` null; may set `failure_type` (e.g. **RETRIEVAL_MISS** if no retrieval rows).
  - **llm:** `claude_llm_judge_v1` — requires prior **`generation_results`** row; `used_llm_judge=true`; scores + **groundedness** + normalized **failure_type**; **`cost_usd`** = **generation + judge** USD from `estimate_usd_from_tokens` for each phase. If **both** `ANTHROPIC_INPUT_USD_PER_MILLION_TOKENS` and `ANTHROPIC_OUTPUT_USD_PER_MILLION_TOKENS` are ≤ 0 (pricing off), or both token counts are unknown for a phase, persist **`NULL`** — never a fake **0** from disabled pricing. A **true zero** estimate (e.g. zero reported tokens with rates on) may be stored as **0**.
- Persisted **`failure_type`** must be a value from `FailureType` after `normalize_failure_type()` (unknown labels → **UNKNOWN**).
- Must remain explainable; keep heuristic path for regression / no-API-key runs.

## Metrics
- No fake or hardcoded benchmark numbers in `PROJECT_METRICS.md`  
- Aggregations from stored rows only (`generate_contextlens_metrics.py`)  
- **`total_latency_ms`** is caller-supplied sum of measured phase latencies (heuristic: retrieval + eval; full: retrieval + generation + eval).  
- **Evaluator buckets** (see `app/domain/evaluator_bucket.py`): **LLM** if `used_llm_judge` OR `metadata_json.evaluator_type == 'llm'`; else **heuristic**.  
- **Score / failure-type / cost averages** are computed **per bucket** (`avg_*_llm`, `avg_*_heuristic`, `failure_type_counts_llm`, …). **No blended** `avg_faithfulness` across both.  
- **`total_traced_runs`**: runs with retrieval + evaluation (any bucket). **`total_traced_runs_llm`** / **`total_traced_runs_heuristic`**: same join, filtered by evaluation row bucket.  
- **`llm_judge_call_rate`**: `COUNT(used_llm_judge IS TRUE) / COUNT(evaluation_results)` over **all** rows; **`None` / “not available”** when the denominator is 0; **`0.0`** when rows exist but none used the LLM judge.  
- **`avg_evaluation_cost_per_run_usd_*`**: `AVG(cost_usd)` within that bucket where `cost_usd IS NOT NULL` only; all-NULL in a bucket → **`None`** (not **0**).  
- **N/A vs zero (reports):** averages with no samples are **not available**; integer **counts** may legitimately be **0**; do not coerce missing averages to **0** in aggregation or Markdown.  

## Docs rule
- `PROJECT.md` = architecture + status  
- `CURRENT_STATE.md` = progress  
- `TASK.md` = immediate next step  
- `DECISIONS.md` = constraints  

After each meaningful implementation task, review and align **`PROJECT.md`**, **`DECISIONS.md`**, **`TASK.md`**, and **`CURRENT_STATE.md`** when the change affects architecture, scope, workflow, schema, metrics, or evaluation behavior. Do not document unimplemented work as done.

If something conflicts → update `DECISIONS.md` explicitly, then align other docs.

### Metrics Integrity Decision

All metrics must be computed from stored run and evaluation data.
No manual or estimated metrics are allowed.

Rationale:
- Prevents misleading claims
- Ensures reproducibility
- Aligns with benchmarking best practices

---

### Trace Schema Decision

Dedicated tables include:
- datasets, query_cases, pipeline_configs, runs, retrieval_results, **generation_results**, evaluation_results

Rationale:
- Enables experiment tracking
- Supports metric aggregation
- Decouples ingestion from evaluation

---

### Embedding Model Decision

Using all-MiniLM-L6-v2 (384-dim vectors)

Rationale:
- Lightweight and fast
- Works well with pgvector
- No external API dependency

### Backend test embedding shim

`backend/tests/conftest.py` (session autouse) replaces `embed_text` / `embed_texts` on **`app.services.embedder`** and re-binds the copies held by **`text_document_ingest`** and **`retrieval`** with **deterministic 384-d L2-normalized fake vectors** (no HuggingFace download).

Rationale:
- Without a local model cache or network, `SentenceTransformer(...)` caused ingest to fail → **`POST /documents`** surfaced as **422** (“Failed to process document…”), cascading to ~15 unrelated test failures — **not** tied to pricing/metrics changes.
- Per-test `monkeypatch` on `embed_text` / `embed_texts` still overrides the shim for targeted error-path tests.

### Tracing Activation Decision

Trace schema is actively used by the backend.

- Retrieval + optional generation + evaluation persisted for benchmark flows
- Evaluation results stored per run (heuristic or LLM)

Rationale:
- Enables real benchmark tracking
- Supports reproducible metrics
- Aligns system behavior with `PROJECT_METRICS.md` (generated from DB)

---

### Benchmark workflow decision

- **Seed:** `backend/scripts/seed_benchmark.py` — idempotent quickstart registry.
- **Run:** `backend/scripts/run_benchmark.py` — `--eval-mode heuristic` (default) or **`full`** (LLM generation + judge per **`LLM_PROVIDER`**, default **OpenAI**; optional **Anthropic**; requires active provider API key).
- **Metrics:** `backend/scripts/generate_contextlens_metrics.py` + `app/metrics/aggregate.py`.

Rationale: reproducible paths from DB → traced rows → Markdown without hand-written benchmark numbers.

---

### Generation storage decision

Generated answers live in **`generation_results`** (1:1 `run_id`), not only in `metadata_json`, for stable inspection and future APIs.

Rationale: clear separation from scores; supports faithfulness against stored text.

---

### Run inspection API decision

- **`POST /api/v1/runs`** — **RQ + Redis** for `eval_mode=full` (not in-process `BackgroundTasks`). Body: integer `query_case_id`, `pipeline_config_id`, `eval_mode` `heuristic`|`full`, optional `document_id` (must exist on `documents` or **404**; passed through to `search_chunks` for corpus scope). **`eval_mode=heuristic`:** synchronous inline (**201**) — `create_and_execute_run_from_ids` commits after retrieval (`running` → `retrieval_completed`) then heuristic eval → `completed`. **`eval_mode=full`:** validates prerequisites + API key, creates run as `running`, **commits**, enqueues **`contextlens_full_run`** job, returns **202** + `{ run_id, status, eval_mode, job_id }`. Worker runs `run_full_benchmark_pipeline` (resume-aware: skips terminal `completed`/`failed`; continues from `running` / `retrieval_completed` / `generation_completed`). **Retries:** RQ **3 attempts** (1 + 2 retries) with backoff on retryable errors; **`ValueError`/`TypeError`** → mark `failed`, no retry; after retries exhausted **`failed`** via `on_failure` → **`mark_run_failed_sync`** uses a **sync** SQLAlchemy + **psycopg** connection (URL derived from **`DATABASE_URL`**: `+asyncpg` → `+psycopg`), **not** `asyncio.run`, so RQ failure callbacks never hit “running event loop” / asyncpg loop-binding issues. **Redis lock** per `run_id` reduces duplicate concurrent execution. **503** if `eval_mode=full` and `claude_api_key` missing/empty, or **Redis unreachable** (cannot enqueue). **502** only on synchronous Anthropic errors (heuristic path); **404** if query case, pipeline config, or document row missing.
- **`GET /api/v1/runs`** — paginated listing, filters (`dataset_id`, `pipeline_config_id`, `evaluator_type`, `status`), newest first.
- **`GET /api/v1/runs/config-comparison`** — aggregates over **traced runs** only: `runs` with ≥1 `retrieval_results` row **and** an `evaluation_results` row, joined for latencies/scores; evaluator bucket filter uses the same SQL as `evaluator_bucket.py` (`er` alias). Default **`evaluator_type=both`** returns **separate** `heuristic` and `llm` metric rows per config (`buckets`); **`combine_evaluators=true`** merges buckets into one row per config. Requested `pipeline_config_ids` with no traced runs appear with **`traced_runs: 0`** and empty failure maps.
- **`GET /api/v1/runs/{run_id}`** — single trace (`run_detail`).
- **`POST /api/v1/runs/{run_id}/requeue`** — see **Durable full-run operations** (same queue/worker as `eval_mode=full`).
- **`GET /api/v1/runs/dashboard-analytics`** — **read-only** analytics endpoint returning 4 sections: **time_series** (daily aggregates over 90 days — run count, completed/failed, avg latency, avg cost, failure count; excludes `NO_FAILURE`), **latency_distribution** (min/max/avg/median/p95 per phase: retrieval, generation, evaluation, total — uses `percentile_cont` for median/p95), **failure_analysis** (overall counts + percentages, per-config breakdown, 10 most-recent failed runs), **config_insights** (per-pipeline config: traced runs, avg latency, avg cost, avg scores, top failure type). Schema: `app/schemas/dashboard_analytics.py`; service: `app/services/dashboard_analytics.py`. Registered in **`api/runs.py`** next to **`/dashboard-summary`**. **404** while **`/dashboard-summary` returns 200** ⇒ **stale uvicorn** (restart **`backend`** / **`uvicorn`**), not a missing route. No mutation, no enqueue.
- **`GET /api/v1/runs/dashboard-summary`** — read-only observability payload for the benchmark UI **Dashboard** tab: **`total_runs`**, **`status_counts`** (``completed`` / ``failed`` / ``in_progress``), **`evaluator_counts`** (distinct runs with heuristic vs LLM evaluation rows + runs without evaluation), **latency averages** over non-null columns on ``runs``, **cost** totals/averages/counts from ``evaluation_results.cost_usd`` (**``None``** = N/A — not coerced to zero; aligns with **`aggregate.py`** / **`PROJECT_METRICS.md`** semantics), **`failure_type_counts`** from evaluations, **`recent_runs`** (newest 20 with status, evaluator bucket, latencies, cost, failure type). No mutation, no enqueue.
- **`GET /api/v1/runs/{run_id}/queue-status`** — inspection: **`pipeline`** `heuristic`|`full` (same inference as requeue), **`run_status`**, whether the **Redis lock** `contextlens:full_run_lock:{run_id}` exists (after **stale-lock** cleanup), best-effort **`job_id`** + RQ status by scanning **`contextlens_full_run`** registries for jobs whose first arg is `run_id` (**not** stored on `runs`), and **`requeue_eligible`** (structural rules + lock only — **not** API key / enqueue). **Stale lock:** if the best-effort RQ job is **`failed`** / **`stopped`** / **`canceled`** and `runs.status` is **`running`** or **`failed`**, the API **deletes** the lock key so operators are not blocked until TTL (~1h) after a dead worker. Unexpected RQ scan errors → logged, **`job_id`/`rq_job_status` null**, no **500** from that path. **Heuristic** runs return **200** without Redis. **503** if Redis is unreachable for a **full** pipeline run.
- **Runs router — numeric `run_id` segments:** In `app/api/runs.py`, **`GET /runs/{run_id}`**, **`GET /runs/{run_id}/queue-status`**, and **`POST /runs/{run_id}/requeue`** use Starlette’s **`{run_id:int}`** path template (integer converter). That way a literal path segment like **`dashboard-summary`** is **not** bound to `run_id` (plain **`/{run_id}`** with a Python `int` annotation still matches the segment first and returns **422**). Static routes **`/runs/dashboard-summary`** and **`/runs/config-comparison`** stay reachable even if dynamic routes are registered earlier. **Restart the API** after deploy so workers load the updated router (Compose bind-mounts `./backend`, but **uvicorn does not auto-reload** unless you enable `--reload`).

Rationale: run analysis and A/B config comparison without ad hoc SQL; optional HTTP trigger for demos/UI without duplicating benchmark logic; same bucket definitions as global metrics.

---

### Durable full-run operations (dev / ops contract)

- **Runbook:** `docs/DEV_FULL_RUN_QUEUE.md` is the operational source of truth: components, **failure / retry / lock** semantics, **restart safety** (API vs worker vs Redis), Compose vs hybrid **DATABASE_URL** (host **5433** when DB is Compose-mapped), **E2E checklist** (**§5**), **validation log** (**§8**), **§5b** automated regression commands, troubleshooting.
- **Docker Compose secrets:** **`docker-compose.yml`** injects **`OPENAI_API_KEY`**, **`LLM_PROVIDER`**, and **`CLAUDE_API_KEY`** from the host into **backend** and **worker** so **`eval_mode=full`** can call the configured provider; export keys before **`docker compose up --build`**. **`backend`** and **`worker`** use the **same image** (**`contextlens-backend:latest`**) so a single **`docker compose build`** refreshes the RQ worker too (avoids a **worker** image missing **`openai`** while **backend** was rebuilt). **`backend/Dockerfile`** verifies **`import openai`** (and **`anthropic`**) after **`pip install .`** so bad dependency resolution fails at **build** time.
- **Pre-flight:** `backend/scripts/check_redis_for_rq.py` (Redis PING) for local bootstrap / CI gates.
- **Durability:** jobs survive **API** process restarts; they do **not** survive **Redis data loss**.
- **HTTP re-enqueue:** **`POST /api/v1/runs/{run_id}/requeue`** — pushes another **`contextlens_full_run`** job for the **same** `run_id` (no new run row). **Eligible** only when `status` is **`running`**, **`retrieval_completed`**, **`generation_completed`**, or **`failed`**; not **`completed`**; not **heuristic-only** (evaluation row in heuristic bucket with no `generation_results` row); **active provider API key** required (**`OPENAI_API_KEY`** when **`LLM_PROVIDER=openai`** default, else **`CLAUDE_API_KEY`** when **`LLM_PROVIDER=anthropic`**); **409** if Redis lock `contextlens:full_run_lock:{run_id}` still exists **after** stale-lock reconcile (same rules as **`GET /queue-status`**: RQ **`failed`**/**`stopped`**/**`canceled`** + run **`running`**/**`failed`** → lock deleted); **503** if Redis enqueue fails or API key missing. **`document_id`** for the job is inferred from retrieval hits (single distinct `document_id`) or **`None`**. If status was **`failed`**, the service **rewrites** `runs.status` to **`generation_completed`** (when a `generation_results` row exists), else **`retrieval_completed`** (when retrieval rows exist), else **`running`**, then **commits**, so the worker (which no-ops on **`failed`**) can resume. Structural eligibility is shared with **`GET /runs/{run_id}/queue-status`** (`evaluate_structural_requeue_eligibility` + lock).
- **HTTP queue inspection:** **`GET /api/v1/runs/{run_id}/queue-status`** — does **not** enqueue or mutate **`runs`**; may **delete** a stale Redis lock when RQ shows a terminal failed job and the run is still **`running`**/**`failed`**; does not guarantee a visible job after RQ TTL/eviction; operators use it before **`POST /requeue`** to see lock + best-effort job state.
- **Worker / API parity:** both must share the same **`DATABASE_URL`** and compatible **`REDIS_URL`** (same logical Redis DB as enqueue uses).
- **LLM provider (generation + judge):** Default **`LLM_PROVIDER=openai`** (`Settings.llm_provider`). **Generation** (`rag_generation`) calls **OpenAI Responses API**; **LLM judge** (`llm_judge_evaluation`) calls **Chat Completions** with **`response_format={"type": "json_object"}`** and preserves parse retry + **`judge_prompt_version`** metadata. Optional **`LLM_PROVIDER=anthropic`** uses **AsyncAnthropic** for both. **`require_llm_api_key_for_full_mode`** gates **`POST /runs`** (`eval_mode=full`) and **`POST /requeue`**. **`estimate_usd_from_tokens`** uses **`OPENAI_*`** or **`ANTHROPIC_*`** per-million rates matching the active provider (no silent cross-pricing). Judge metadata includes **`llm_provider`** (`openai` \| `anthropic`); logical **`EVALUATOR_ID`** / bucket strings remain **`claude_llm_judge_v1`** / **`llm`** for historical compatibility.

---

### Benchmark registry API decision (read + write)

- **`GET /api/v1/datasets`** (list, newest first) and **`GET /api/v1/datasets/{id}`** — unchanged.
- **`POST /api/v1/datasets`** (**201**) — body matches model: **`name`**, optional **`description`**, optional **`metadata_json`**.
- **`PATCH /api/v1/datasets/{id}`** (**200**) — partial update; **404** if id missing; **422** on invalid body (e.g. empty name).
- **`GET /api/v1/query-cases`** with optional **`dataset_id`** filter; **404** when the filter references a missing dataset. **`GET /api/v1/query-cases/{id}`** for detail.
- **`POST /api/v1/query-cases`** (**201**) — requires **`dataset_id`** (FK must exist → else **404**), **`query_text`**, optional **`expected_answer`** / **`metadata_json`**.
- **`PATCH /api/v1/query-cases/{id}`** (**200**) — partial update; **404** for missing row or invalid **`dataset_id`** FK.
- **`GET /api/v1/pipeline-configs`** (list, `id` ascending) and **`GET /api/v1/pipeline-configs/{id}`** — retrieval parameters only; **`eval_mode`** stays on **`POST /runs`**, not on `pipeline_configs`.
- **`POST /api/v1/pipeline-configs`** (**201**) / **`PATCH /api/v1/pipeline-configs/{id}`** (**200**) — **`name`**, **`embedding_model`**, **`chunk_strategy`**, **`chunk_size`**, **`chunk_overlap`**, **`top_k`**, optional **`metadata_json`**; **422** when **`chunk_overlap` > `chunk_size`** (including after PATCH). **404** on PATCH for unknown id.
- **Responses** use the same read DTOs as GET; **`metadata_json`** is exposed on datasets and pipeline configs for parity with the DB (query cases already exposed it).
- **DELETE (safe, no silent trace loss):**
  - **`DELETE /api/v1/datasets/{id}`** — **204** if the dataset exists and has **no** `query_cases`; **404** if missing; **409** if any `query_cases` reference it (blocks delete even though Postgres has **`ON DELETE CASCADE`** from datasets → query_cases, which would also cascade-delete runs — the API never uses that path while query cases exist).
  - **`DELETE /api/v1/query-cases/{id}`** — **204** if no `runs` reference it; **404** missing; **409** if any run references it (Postgres would **`ON DELETE CASCADE`** runs if we deleted the query case without this check — blocked so trace history is not removed implicitly).
  - **`DELETE /api/v1/pipeline-configs/{id}`** — **204** if no `runs` reference it; **404** missing; **409** if runs exist (aligns with DB **`ON DELETE RESTRICT`** on `runs.pipeline_config_id`).
- Services: **`dataset_delete.py`**, **`query_case_delete.py`**, **`pipeline_config_delete.py`**; exceptions **`DatasetDeleteConflictError`**, **`QueryCaseDeleteConflictError`**, **`PipelineConfigDeleteConflictError`** → **409** with explicit **`detail`**.

Rationale: UI and scripts can manage registry rows without SQL; deletes are explicit and refuse to orphan or silently wipe traced runs.

---

### Frontend benchmark UI decision

- **First product slice** in `frontend/`: consumes existing `/api/v1` routes only (no new backend for this flow). **Navigation:** **client-side routing** via `react-router-dom` `BrowserRouter`; URL is the source of truth for view selection. **Routes:** `/benchmark` (run form), `/runs` (recent runs list), `/runs/:runId` (run detail deep link), `/compare` (config comparison), `/dashboard` (observability). `/` and unknown paths redirect to `/benchmark`. Invalid (non-numeric) `:runId` shows an inline error. Browser back/forward and refresh are supported. **Vite dev** proxies `/api` → **`BACKEND_PROXY_TARGET`** (default **`http://127.0.0.1:8002`** in `vite.config.ts`; use `frontend/.env.development.local` for e.g. Docker API on **:8000** — see `frontend/.env.example`). Optional **`VITE_API_BASE`** to bypass the proxy (ensure CORS). **SPA fallback:** Vite dev/preview handles history API fallback by default; production deploys (nginx, etc.) must route non-`/api` paths to `index.html`.
- **Registry management (Run tab):** **`RegistryPanel`** — create / edit / delete **datasets**, **query cases** (per-dataset list + `GET /query-cases?dataset_id=`), and **pipeline configs** using the same HTTP registry APIs; **`409`** delete conflicts surface in-panel; **`loadRegistry({ preserveSelection: true })`** after mutations keeps run-form picks when rows still exist; document scope resets to **all chunks** if the selected document disappears from **`GET /documents`**.
- **Document upload:** **`UploadDocumentPanel`** — **`FormData`** to **`POST /api/v1/documents`**, local errors only (does not use the global run alert for upload failures); on success list refresh + auto-select **`document_id`**.
- **Config comparison** must not merge heuristic and LLM buckets unless the user explicitly enables **`combine_evaluators`** (matches backend default separation).
- **Dashboard — observability:** **`DashboardPanel`** on the **Dashboard** tab loads **`GET /runs/dashboard-summary`** (run + evaluator counts, latency averages, cost with **N/A** vs **$0** copy, failure-type table, recent runs) **and** **`GET /runs/dashboard-analytics`** (time series, latency distribution, failure breakdown, config insights) in parallel. Four dedicated sub-panels: **`DashboardTrendPanel`** (daily run counts with bar chart), **`LatencyDistributionPanel`** (min/avg/median/p95/max per phase), **`FailureBreakdownPanel`** (overall + per-config + recent failed runs), **`ConfigInsightsPanel`** (per-pipeline scores/cost/top failure). Format helpers in **`dashboardAnalyticsFormat.ts`** (pure functions, 11 unit tests). Optionally loads **`GET /runs/config-comparison`** for up to **12** pipeline config ids from the loaded registry (both buckets, compact tables — no new charting stack). **Exports (v1):** **Export JSON** bundles `exported_at` + in-memory **`dashboard_summary`** + **`dashboard_analytics`**; **Export CSV** flattens summary metrics, failure counts, recent runs, latency distribution, daily time series, and config insights — all from already-fetched payloads (**no** new backend report generator). **Run detail** **Export JSON** downloads the current **`GET /runs/{id}`** object as pretty-printed JSON (`exportDownload.ts`).
- **Dashboard — validation scope (honesty):** The **`/dashboard`** **shell** (layout, static copy, nav) can render **without** a reachable API. **Functional** dashboard validation requires **backend running** and successful real responses from **`GET /api/v1/runs/dashboard-summary`** and **`GET /api/v1/runs/dashboard-analytics`** (or explicit documented error states), with the UI reflecting that payload. Observing **invalid `:runId`** or similar UX **while the API is down** validates **routing/error copy only**, **not** end-to-end dashboard or run-detail behavior. **Recorded live check (2026-03-21):** both endpoints **200** (empty + seeded **6** heuristic runs); **Vite** **`/api`** proxy to **:8002** verified; **`docker compose restart backend`** needed when **`/dashboard-analytics`** **404**s on a long-lived uvicorn (stale routes). **`DashboardPanel`** loading/success/error/empty: **Vitest** + real JSON; **headed browser** pass optional.
- **Run detail — queue:** **`RunQueuePanel`** calls **`GET /runs/{id}/queue-status`** on load, when **`runDetail.status`** changes (so polling that moves a full run to **`completed`** / **`failed`** refreshes eligibility — no stale **`requeue_eligible: true`** UI), on **Refresh**, and after a successful requeue; **`POST /runs/{id}/requeue`** when **`requeue_eligible`** (full pipeline only). **Operator summary (v1):** badge + description derived only from the queue-status JSON (`pipeline`, `requeue_eligible`, `lock_present`, `detail`, RQ fields) via **`queueOperatorState.ts`** — no fabricated server states. Local loading / error / success copy; **Requeue** disabled while a request is in flight to avoid double-submit.
- **Queue browser (`/queue`):** same queue-status + requeue contracts as run detail; **Operator readout** column + recovery hint; after successful requeue, row queue-status refresh + **`GET /runs`** list reload (bounded slices) so run **Status** updates without bulk or polling. **No** new admin API.
- **Unit tests** (Vitest): see **`PROJECT.md`** automated checks (**~190** tests); includes **`queueOperatorState`**, **`queueBrowserLoad`**, **`QueueBrowserPanel`**, **`RunQueuePanel`**, **`exportDownload`**, dashboard + routing suites, etc.; full **`eval_mode=full`** flow remains manual against live API + worker.

---

### LLM judge parsing decision

- Judge model text is parsed via **`llm_judge_parse`** (extract JSON + coerce scores to 0..1 + normalize `failure_type`).
- Malformed JSON → empty scores where needed, **`UNKNOWN`** failure default, warnings list; **`judge_parse_ok`** in metadata flags structural success (no critical parse / extract errors per `_compute_judge_parse_ok` in `llm_judge_evaluation.py`).
- **Prompt contract version:** every LLM judge evaluation persists **`judge_prompt_version`** (constant **`JUDGE_PROMPT_VERSION`** in `llm_judge_evaluation.py`, currently **`claude_llm_judge_v2`**) alongside existing **`evaluator`** / **`evaluator_type`** (`claude_llm_judge_v1` / `llm`) so rows remain bucket-compatible while the prompt/parse contract can be traced.
- **One in-process retry (not RQ):** if the **first** model response yields **`judge_parse_ok == false`**, **`evaluate_with_llm_judge`** performs **exactly one** additional judge API call. Transport failures (**no** successful response) are **not** retried here (unchanged propagation to caller / RQ). Metadata: **`judge_initial_parse_ok`**, **`judge_retry_attempted`**, **`judge_retry_succeeded`**; judge token counts on the result **sum** both calls when a retry ran (for **`cost_usd`** estimates).
- **Observability (judge `metadata_json`, no migration):** `judge_score_clamping_occurred`, `judge_scores_raw` (pre-clamp values), `judge_raw_failure_type` (pre-normalize label), `judge_parse_warning_count` (length of warning list). Persisted column **`failure_type`** remains normalized only.
- **Regression tests:** `tests/test_llm_judge_parse.py`, **`tests/test_llm_judge_parse_golden.py`** (fixtures under `tests/fixtures/judge_outputs/`), **`tests/test_llm_judge_evaluation_retry.py`**.

Rationale: analysis and dashboards must not crash on bad judge output; debugging needs visibility into clamp/normalize, prompt generation, and retry without changing persisted taxonomy or queue semantics.
