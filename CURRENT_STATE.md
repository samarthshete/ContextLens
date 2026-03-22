# CURRENT STATE

## Phase
**Phase 6 — Dashboard analytics (done). Run detail diagnosis (first slice — client-side heuristics on existing run JSON).**

---

## Completed

### Phase 1 — Foundation
- FastAPI app, config, async SQLAlchemy
- PostgreSQL 16 + pgvector (Docker)
- Alembic migrations (sole schema source)
- `/health`, CORS, session management

### Phase 2 — Ingestion
- Document upload (PDF, TXT, Markdown)
- Parsing (`parser.py`)
- Chunking (fixed + recursive)
- Validation (file type, size, chunk limits)
- Local file storage
- **Shared ingest service** (`app/services/text_document_ingest.py`) used by API and benchmark scripts

### Phase 3 — Embeddings + Retrieval
- Embeddings: all-MiniLM-L6-v2 (384-dim, normalized)
- pgvector storage on `chunks.embedding`
- HNSW cosine index
- Retrieval API (`POST /api/v1/retrieval/search`)
- Score = `1 - cosine_distance`

### Phase 4 — Tracing + full RAG + trustworthy reporting
- Trace tables: datasets, query_cases, pipeline_configs, runs, retrieval_results, **generation_results**, evaluation_results (**groundedness**)
- Benchmark: `seed_benchmark.py`, `run_benchmark.py` (`heuristic` | `full`); **evidence dataset** — `benchmark-datasets/evidence-rag-v1/` + `scripts/seed_evidence_benchmark.py` / `run_evidence_benchmark.py` / `export_evidence_benchmark_summary.py` + `app/services/benchmark_evidence_seed.py` (real traced runs; results in **`docs/benchmark-results.md`**); **`rag_systems_retrieval_engineering_v1`** — `backend/benchmark_data/rag_systems_retrieval_engineering_v1/` + `scripts/seed_rag_systems_benchmark.py` / `run_rag_systems_benchmark.py` / `export_rag_systems_benchmark_summary.py` + `app/services/benchmark_rag_systems_seed.py` (three scoped ingests for chunk/top_k variants; measured narrative + numbers in **`docs/benchmark_results_rag_systems_retrieval_engineering_v1.md`**)
- Run lifecycle through **`completed`** or **`failed`**
- **Heuristic** vs **LLM** evaluators (`evaluator_type` + `used_llm_judge`)
- **Metrics:** `aggregate.py` — split heuristic / LLM; **N/A vs zero** semantics; `generate_contextlens_metrics.py` + **`PROJECT_METRICS.md`** semantics doc; **`cost_usd`** = gen + judge estimate, **NULL** when pricing off / unknown (no fake zero)
- **Benchmark registry:** **`GET`** + **`POST`/`PATCH`/`DELETE`**
- **Runs API:** `POST /runs`, **`GET /runs/dashboard-summary`**, **`GET /runs/dashboard-analytics`** (read-only aggregates + richer analytics), **`POST /runs/{id}/requeue`** (eligible full runs only; stale-lock reconcile before lock **409**), **`GET /runs/{id}/queue-status`** (RQ inspection + stale-lock cleanup + safe RQ scan), list, detail, config comparison; **RQ `on_failure`** → **`mark_run_failed_sync`** (sync **psycopg**, not **`asyncio.run`**)
- **Full runs:** Redis + RQ + worker + **`docs/DEV_FULL_RUN_QUEUE.md`**
- **LLM judge:** **`judge_prompt_version`**, parse retry, golden fixtures; **OpenAI** default for judge + generation (**`LLM_PROVIDER`**), optional **Anthropic**
- **Frontend (pre-routing):** tab-based SPA; Run tab **registry CRUD** + workflow/corpus-scope copy + document upload; **Dashboard** tab — run/latency/cost/failure aggregates (`GET /runs/dashboard-summary`) + recent runs + optional per-config comparison snapshot; **Run detail** **`RunQueuePanel`** (queue-status refetches when run **`status`** updates so completed full runs match **`requeue_eligible`** from the API); Vite proxy default **`127.0.0.1:8002`** (matches Docker Compose **backend** host port). **Docker:** **`backend`** + **`worker`** share **`contextlens-backend:latest`** — **`docker compose build`** / **`up --build`** updates both; **`Dockerfile`** verifies **`import openai`** after **`pip install`**.
- Docs: `BENCHMARK_WORKFLOW.md`, `METRICS_INSTRUMENTATION.md`, `FULL_RAG_EXAMPLE.md`, `DEV_FULL_RUN_QUEUE.md`

### Phase 5 — Client-side routing
- **`react-router-dom`** `BrowserRouter` added to frontend
- **Routes:** `/benchmark` (run form), `/runs` (recent runs list), `/runs/:runId` (run detail deep link), `/documents/:documentId` (document metadata + chunk texts from existing document APIs), `/compare` (config comparison), `/dashboard` (observability)
- `/` and unknown paths redirect to `/benchmark`
- URL is source of truth for view selection — replaced `useState<View>` with `routeView` prop from router
- All `setView()` calls replaced with `navigate()` — browser back/forward and refresh work
- Deep links: `/runs/42` directly opens run detail and fetches from API
- Invalid (non-numeric) `:runId` shows inline error message
- Run detail input field syncs URL on change (`replace: true`)
- Dashboard, runs list, comparison all open from nav buttons via `navigate()`
- **7 new routing tests** (route rendering per view, deep link, invalid ID, nav active state)
- **45** total frontend Vitest tests at Phase 5 exit; build + lint clean

### Phase 6 — Dashboard analytics
- **Backend:** `GET /api/v1/runs/dashboard-analytics` — new read-only endpoint
  - Schema: `app/schemas/dashboard_analytics.py` (TimeSeriesDay, LatencyDistribution, LatencyDistributionSection, FailureByConfig, RecentFailedRun, FailureAnalysisSection, ConfigInsight, DashboardAnalyticsResponse)
  - Service: `app/services/dashboard_analytics.py` — 4 async query functions:
    - `_time_series`: daily aggregates over 90 days (run count, completed/failed, avg latency, avg cost, failure count excluding NO_FAILURE)
    - `_latency_distribution`: min/max/avg/median(p50)/p95 per phase (retrieval, generation, evaluation, total) using `percentile_cont`
    - `_failure_analysis`: overall failure counts + percentages, per-config breakdown, 10 most-recent failed runs
    - `_config_insights`: per-pipeline config traced runs, completed/failed counts, avg latency, avg/total cost, avg scores (completeness, retrieval_relevance, context_coverage, faithfulness), latest run, top failure type
  - Route registered in `api/runs.py` before config-comparison
  - **3 new tests** in `test_dashboard_analytics_api.py` (response shape, seeded data correctness, non-breaking of existing endpoint)
  - **Dashboard summary retrieval percentiles:** **`GET /runs/dashboard-summary`** **`latency`** includes **`retrieval_latency_p50_ms`** / **`retrieval_latency_p95_ms`** from PostgreSQL **`percentile_cont`** over persisted **`runs.retrieval_latency_ms`** (non-null only); shared aggregation in **`app/services/phase_latency_distribution.py`** (also powers **`dashboard-analytics`** phase latency — no duplicate SQL). **`null`** when no samples.
  - **End-to-end run latency (seconds):** **`latency.end_to_end_run_latency_avg_sec`** / **`end_to_end_run_latency_p95_sec`** from non-null **`runs.total_latency_ms`** (same query as **`avg_total_latency_ms`**; P95 = **`percentile_cont(0.95)`**; sec = ms ÷ 1000). **`GET /runs/dashboard-analytics`** exposes the same avg/p95 as top-level **`end_to_end_run_latency_*_sec`** (derived from **`latency_distribution.total`** — no second query).
  - **Dashboard scale (`summary.scale`):** **`benchmark_datasets`**, **`total_queries`**, **`total_traced_runs`** (retrieval + eval rows), **`configs_tested`** (distinct **`pipeline_config_id`** on runs), **`documents_processed`** (`status='processed'`), **`chunks_indexed`** (chunk row count) — **`DECISIONS.md`** + **`test_dashboard_summary_api.py`**
  - **3 tests** in **`test_phase_latency_distribution.py`** (retrieval percentiles, **`total_latency_ms`** distribution, all-null retrieval)
  - **168** total backend tests (all green with DB; includes **`test_dashboard_summary_api.py`** cost-per-run + **`test_config_comparison_scores.py`** — config score spread unit tests without DB teardown; **`test_write_protection_api.py`**, **`test_evidence_dataset_load.py`**, **`test_rag_systems_dataset_load.py`** — corpus grounding; **`pytest.mark.no_database_cleanup`** skips DB teardown for those file-only tests)
- **Frontend:**
  - Types: `TimeSeriesDay`, `LatencyDistribution`, `LatencyDistributionSection`, `FailureByConfig`, `RecentFailedRun`, `FailureAnalysisSection`, `ConfigInsight`, `DashboardAnalyticsResponse` in `api/types.ts`
  - Client: `dashboardAnalytics()` method in `api/client.ts`
  - 4 panel components: `DashboardTrendPanel`, `LatencyDistributionPanel`, `FailureBreakdownPanel`, `ConfigInsightsPanel` — **richer observability v1 (no new API):** stacked **per-day** run trend bars (completed / failed / other + legend + **Daily numbers** table with **Failed** column); **latency** horizontal bars for median / p95 / max per phase (tables retained); **failure** overall bar rows above exact-count tables (`failure-overall-bars`); **config insights** row highlight for failure-prone configs (`cl-config-insight-row--attention`) alongside existing fast/high-relevance highlight
  - Format helpers: `dashboardAnalyticsFormat.ts` (formatScore, formatPercent, formatDate, formatDistRow, timeSeriesMaxRuns, sortedFailureCounts, plus chart helpers: `timeSeriesDayStack`, `latencyPhaseScaleMs` / `barWidthPct`, `failureTypeBarPercents`, `configInsightRowClasses`)
  - `DashboardPanel` fetches summary + analytics in parallel via `Promise.all`
  - **`dashboardAnalyticsFormat.test.ts`**, **`dashboardFormat.test.ts`** + expanded **`DashboardPanel.test.tsx`** (trends chart, failure bars, config row classes; **Latency** card — retrieval **Mean / P50 / P95**; **End-to-end (total)** mean ms + avg/p95 s via **`formatLatencySec`**)
  - Updated mocks in `DashboardPanel.test.tsx` and `routing.test.tsx`
  - **199** total frontend Vitest tests (all green); build + lint clean (includes **dashboard per-run LLM / full-RAG cost**, **config comparison score spread** UI + mocks + **`scoreComparisonFormat.test.ts`**, **run diagnosis** + tuning, **run diff**, **retrieval source** + **document detail route**, **phase timeline**, **runs list filters**, **queue browser** + **`queueOperatorState`**, **export** `exportDownload`)
- **Live dashboard validation (2026-03-21, Local Docker + host Vite):** **`GET /health`** **200**. **`GET /api/v1/runs/dashboard-summary`** and **`GET /api/v1/runs/dashboard-analytics`** **200** with sensible **empty** payloads after **`docker compose restart backend`** (stale process had returned **404** on **`/dashboard-analytics`** until restart). **`scripts/seed_benchmark.py`** + **`run_benchmark.py --eval-mode heuristic`** inside **`backend`** container → **6** completed runs; both dashboard endpoints **200** with **non-empty** time series, latency distribution, summary stats, **`config_insights`**. **Vite dev proxy** (`http://127.0.0.1:5173/api/...` → **:8002**) verified same JSON for both routes. **Loading / success / error / empty** UX for **`DashboardPanel`**: **Vitest** (`DashboardPanel.test.tsx`) + code review; **headed browser** screenshot pass **not** part of this automation. **Frontend:** **`npm run test -- --run`**, **`npm run build`**, **`npm run lint`** — all green.

### Dashboard — cost per run (LLM measured)
- **`GET /runs/dashboard-summary` → `cost`:** **`avg_cost_usd_per_llm_run`** / **`llm_runs_with_measured_cost`** — **LLM-bucket** **`evaluation_results`** with non-null **`cost_usd`** only; **`avg_cost_usd_per_full_rag_run`** / **`full_rag_runs_with_measured_cost`** — same, restricted to runs with **`generation_results`**. Existing **`avg_cost_usd`** = mean per **evaluation row** (label clarified in UI). **`dashboard_summary.py`** also **restores** missing **`scale`** **`COUNT`** block (was referenced but undefined — runtime fix).
- **Frontend:** **`DashboardPanel`** + dashboard export CSV rows; types + mocks updated.
- **Tests:** **`test_dashboard_summary_api.py`** (shape keys + heuristic exclusion + full-RAG seed); **`exportDownload.test.ts`** + **`DashboardPanel.test.tsx`**.

### Config comparison — score spread (decision metrics)
- **Backend:** **`GET /runs/config-comparison`** returns **`avg_faithfulness`** per config row (bucket-scoped **`AVG`** of non-null **`evaluation_results.faithfulness`**) plus **`ConfigScoreComparisonSummary`**: **`best_config_faithfulness`**, **`worst_config_faithfulness`**, **`faithfulness_delta_pct`**, **`best_config_completeness`**, **`worst_config_completeness`**, **`completeness_delta_pct`**. **`evaluator_type=both`** → **`score_comparison_buckets.heuristic`** + **`.llm`**; single bucket or combined → **`score_comparison`**. **`combine_evaluators`:** faithfulness summary fields **null**; completeness spread retained (**`DECISIONS.md`**).
- **Frontend:** **`scoreComparisonDisplay.tsx`**, **`scoreComparisonFormat.ts`**, **`configComparisonMock.ts`** (dashboard Vitest); **`DashboardPanel`** per-bucket snapshot; **`BenchmarkWorkspace`** **`/compare`** — table columns **Avg faith. / Avg comp.** + score cards under each bucket / combined.
- **Tests:** **`backend/tests/test_config_comparison_scores.py`** (6, **`no_database_cleanup`**); **`test_runs_api`** extended; **`DashboardPanel.test.tsx`** LLM bucket score copy; routing/runs mocks use full comparison JSON (inline in **`vi.mock`** to avoid hoist issues).

### Run detail diagnosis (first slice)
- **Frontend only** — uses **`GET /api/v1/runs/{id}`** as today (`retrieval_hits`, `generation`, `evaluation` + `metadata_json`); **no** new backend route for this slice.
- **`runDiagnosis.ts`:** retrieval stats (count, top score, rank gap, copy) + **source concentration** note when **≥3** hits share one **`document_id`**; context quality (chunk **count**, per-rank lengths, thin/**sparse** vs **`top_k`** via `ceil(top_k/3)` cap, duplicate/**prefix** + consecutive **suffix↔prefix** overlap warning); generation+judge tokens/models/cost + **`evaluationScoreRows`** + judge **`metadata_json`** badges; **likely-cause** summary including **explicit lines** for **`RETRIEVAL_PARTIAL`**, **`CHUNK_FRAGMENTATION`**, **`CONTEXT_TRUNCATION`**, **`MIXED_FAILURE`**, **`UNKNOWN`**; **generation vs retrieval** split for **`ANSWER_UNSUPPORTED` / `ANSWER_INCOMPLETE`** when retrieval scores look usable; prior signals (weak retrieval, low coverage, thin context, expensive-but-weak).
- **Components:** `RunDiagnosisSummary`, `RetrievalDiagnosisPanel`, `ContextQualityPanel`, `GenerationJudgeInsightsPanel` — mounted from **`BenchmarkWorkspace`** on the run detail view.
- **Tests:** **`runDiagnosis.test.ts`** (expanded branch coverage for taxonomy, sparse edges, overlap, generation vs retrieval, expensive-weak, clean path, null faithfulness) + **`routing.test.tsx`** **`run-diagnosis-summary`**.
- **Remaining (not done here):** richer narratives, hiding raw JSON behind “Advanced”, automated headed UI snapshots.

### Run diff v1 (run detail)
- **No new backend** — user enters a second run ID; UI calls **`GET /api/v1/runs/{id}`** again and compares to the loaded run.
- **`runDiff.ts`:** deterministic **`DiffVerdict`** per row (`improved` / `worse` / `same` / `unknown`, meaning run **B** vs **A**); reuses **`runDiagnosis`** helpers for retrieval/context; rows for status, hits, top score, rank gap, context size, thin heuristic, generation presence, tokens (display), cost, failure type, key eval scores; **warnings** if query case or pipeline config IDs differ; short **summary** lines in plain English.
- **`RunDiffPanel`:** mounted in **`BenchmarkWorkspace`** after **`GenerationJudgeInsightsPanel`**; **`data-testid="run-diff-panel"`**.
- **Tests:** **`runDiff.test.ts`**, **`RunDiffPanel.test.tsx`** (mocked **`getRun`**).

### Retrieval hit → document source (v1)
- **No new backend** — `RetrievalHitOut` already includes **`document_id`**; no filename/title in run-detail JSON.
- **Frontend:** **`retrievalSourceFormat.ts`** builds optional title lookup from the same **`documents`** list loaded with the registry on the Run tab; **`formatRetrievalDocumentLabel`**, **`analyzeRetrievalSourceDiversity`**, **`retrievalSourceDiversityNote`** (e.g. all hits from one doc vs multiple).
- **`RetrievalHitsSection`** — run detail retrieval block; per-hit **Source** line (clickable **`Link`** to **`/documents/:documentId`** when `document_id` is present) + diversity note; hint when titles are missing until registry loads.
- **`DocumentDetailPanel`** — **`GET /api/v1/documents/{id}`** + **`GET /api/v1/documents/{id}/chunks`**; metadata, optional `metadata_json`, full chunk list for provenance; **Back** uses browser history.
- **Tests:** **`retrievalSourceFormat.test.ts`**, **`RetrievalHitsSection.test.tsx`** (source link `href`, plain fallback when `document_id` absent), **`DocumentDetailPanel.test.tsx`**, **`routing.test.tsx`** (`/documents/:id`).

### Recent runs — search & filter (v1)
- **No new backend** — uses existing **`GET /api/v1/runs`** query params: **`status`**, **`evaluator_type`** (`heuristic` \| `llm`), **`dataset_id`**, **`pipeline_config_id`**, plus **`limit`** / **`offset`** (unchanged pagination).
- **Frontend:** **`api.listRuns`** + **`ListRunsParams`** in **`api/types.ts`**; **`runsListQuery.ts`** (`buildListRunsApiParams`, **`narrowRunsOnPage`** for honest client-side narrowing on **loaded page rows** only); **`RunsFilterBar`** on **`/runs`** inside **`BenchmarkWorkspace`**; **`benchmark.css`** (`.cl-runs-filter-*`).
- **Copy:** “**Narrow visible rows**” is labeled as **current page only** (run ID, status, query text, evaluator, dataset/pipeline ids, pipeline name) — not a server text search.
- **Tests:** **`runsListQuery.test.ts`**, **`RunsFilterBar.test.tsx`**, **`runsListPage.test.tsx`** (filter → refetch, clear, narrow, **Open** → detail).
- **E2E:** **`e2e/runs-list.spec.ts`** — filter bar + status filter refetch (requires **`npx playwright install`** locally if browsers missing).

### Queue browser (v1)
- **No new backend** — **`GET /runs`** (five parallel status slices: pending, running, retrieval_completed, generation_completed, failed; deduped, newest-first, capped at **45** rows) plus per-row-on-demand **`GET /runs/{id}/queue-status`** and optional **`POST /runs/{id}/requeue`** when the loaded queue-status matches **`shouldShowRequeueButton`** (same rules as **`RunQueuePanel`**).
- **Frontend:** route **`/queue`**, nav **Queue**, **`queueBrowserLoad.ts`**, **`QueueBrowserPanel`**. **Operator readout** column: badges + tooltips from **`queueOperatorState.ts`** — maps only existing queue-status fields (`pipeline`, `requeue_eligible`, `lock_present`, `detail`, `rq_job_status`, `job_id`, `run_status`); states such as **Queue status needed**, **Recovery: can requeue**, **Blocked: worker lock**, **Heuristic (no queue)**, **Not requeue-eligible**, **Queue status error**. Static recovery hint for interrupted/failed full runs; **no auto-polling**; technical columns unchanged for power users.
- **Recovery flow:** successful row **Requeue** → refresh that row’s queue-status → **`loadList(false)`** then success notice (list reload so **Status** column tracks **`GET /runs`** without clearing the notice); **Refresh list** clears the notice.
- **`RunQueuePanel`:** same **`presentationFromQueueStatus`** summary (badge + description) above the raw dl for run detail.
- **Tests:** **`queueOperatorState.test.ts`**, **`queueBrowserLoad.test.ts`**, **`QueueBrowserPanel.test.tsx`** (incl. lock-blocked badge, requeue → list refetch + notice), **`RunQueuePanel.test.tsx`**, **`routing.test.tsx`** (`/queue`).
- **E2E:** **`e2e/queue-browser.spec.ts`** — list row + refresh queue-status (mocked APIs).

### Export / reporting (v1)

- **No new backend routes** — downloads are generated in the browser from data already returned by **`GET /api/v1/runs/{id}`**, **`GET /api/v1/runs/dashboard-summary`**, and **`GET /api/v1/runs/dashboard-analytics`**.
- **Run detail** (`/runs/:runId`): **Export JSON** writes pretty-printed JSON to **`contextlens-run-{run_id}.json`** (`BenchmarkWorkspace` + **`exportDownload.ts`**).
- **Dashboard** (`/dashboard`): **Export JSON** (`contextlens-dashboard.json`) bundles `exported_at` + summary + analytics; **Export CSV** (`contextlens-dashboard.csv`) uses sectioned tables (summary metrics, failure counts, recent runs, latency distribution, daily time series, config insights). Buttons disabled while loading or on fetch error.
- **Tests:** **`exportDownload.test.ts`** (CSV/JSON helpers, filenames, partial payloads), **`DashboardPanel.test.tsx`** (export buttons + `triggerBrowserDownload` spy), **`routing.test.tsx`** (run export + blob content).

### Phase timeline (run detail)
- **Frontend only** — uses `retrieval_latency_ms`, `generation_latency_ms`, `evaluation_latency_ms`, `total_latency_ms` from `GET /api/v1/runs/{id}`.
- **`runTimeline.ts`:** pure helpers — `buildTimelineModel` normalizes phase durations, computes percentages only when valid (component sum ≤ total, total > 0), identifies the dominant phase, and generates a short plain-English summary (e.g. "Generation dominated at 3.1s (75.2% of 4.1s)"). Safe for all null combinations.
- **`PhaseTimeline`** component: renders retrieval / generation / evaluation / total rows with proportional bars (CSS), duration, optional percentage, dominant-phase highlight. Missing phases show "—" (not fake zero). Returns `null` when no timing data at all.
- Mounted in `BenchmarkWorkspace` run detail view after the Summary section, before `RunDiagnosisSummary`.
- Replaces the flat inline "Latencies (ms) — retrieval / generation / evaluation / total" text.
- **Tests:** `runTimeline.test.ts` (11 pure helper tests: full run, heuristic, single phase, overhead, total missing, sum > total, no data, total only, zero durations, fmtMs), `PhaseTimeline.test.tsx` (4 component tests: heuristic render, dominant phase, null data, invalid percentages).
- See **Automated checks** for current Vitest count.

### E2E / visual regression (Playwright)
- **Playwright** added to frontend (`@playwright/test`, chromium only, headless).
- **Config:** `playwright.config.ts` — runs against `vite preview` on port 4173; `webServer` auto-starts preview.
- **API mocking:** `page.route()` intercepts all `/api/v1/*` calls with deterministic fixtures in `e2e/fixtures.ts` — no backend required.
- **14** Playwright tests total: **11** in `e2e/run-detail.spec.ts`:
  1. Heuristic run loads all main sections (diagnosis, timeline, retrieval, context, gen/judge, diff)
  2. Timeline shows retrieval + evaluation rows, generation shows "—"
  3. Full run timeline marks generation as dominant
  4. Retrieval hits show source labels with document IDs
  5. Full run shows evaluation score grid
  6. Diff panel loads comparison run and shows table
  7. Diff panel shows error for non-numeric input
  8. Diff panel rejects same-run comparison
  9. Partial run (no eval/gen) renders without crash
  10. 404 run shows error
  11. Non-numeric run ID shows validation error
- Plus **1** in `e2e/runs-list.spec.ts` (runs list filter bar + status refetch), **1** in `e2e/queue-browser.spec.ts`, and **1** in `e2e/dashboard.spec.ts` (mocked summary + analytics; trend chart + latency panel). Requires browsers installed (`npx playwright install`).

---

## Current limitations

- **Hosted / production-like:** not **enterprise** multi-tenant SaaS. Optional **`CONTEXTLENS_WRITE_KEY`** gates writes (header **`X-ContextLens-Write-Key`**); GET APIs stay readable without it. **`APP_ENV=production`** enforces non-empty write key and non-wildcard **`CORS_ORIGINS`**. OpenAPI **`/docs`** disabled in production profile. **Vercel + Render:** concrete topology, env map, deploy order, and smoke checklist in **`docs/DEPLOYMENT.md` §9**; optional **`render.yaml`** Blueprint; **`frontend/vercel.json`** for SPA rewrites. **Not claimed:** a specific live URL — operators run deploy steps in their own accounts.
- **`GET /api/v1/runs/dashboard-analytics` → 404** while **`/runs/dashboard-summary` → 200:** the **route is implemented** in **`app/api/runs.py`** and mounted under **`/api/v1/runs`**. **Cause:** **stale uvicorn** (process started before the route existed or before bind-mount updates were reloaded). **Fix:** **`docker compose restart backend`** (Compose) or restart **`uvicorn`**. Only use **`docker compose build backend --no-cache`** if you run **without** mounting `./backend` and the **image** is old.
- **RQ:** Run detail **`RunQueuePanel`** + **`/queue`** **Queue browser** expose **queue-status** + row **requeue** when eligible (read-mostly browser; no bulk actions); not a full RQ job browser; Redis loss still loses queue; see runbook
- **`cost_usd`:** **OpenAI** or **Anthropic** per-million rates per **`LLM_PROVIDER`** (not per exact model SKU); semantics are explicit (null vs zero)
- **Judge:** invalid numeric fields in otherwise valid JSON still do **not** alone trigger parse retry; further tuning optional
- **SPA fallback (production):** Vite dev/preview handles history API fallback; production nginx/CDN must route non-`/api` paths to `index.html`

---

## Next task

Optional **run-detail** polish (see **`TASK.md`**); **deeper queue/RQ admin** (bulk job browser, etc.) or further **dashboard chart** polish, or operator-led Phase 4 closure (`docs/DEV_FULL_RUN_QUEUE.md` §5 + §8). **Runs list** filters, **Queue browser** v1 + **operator readout** closure, **dashboard observability charts v1**, and **client-side export** (run JSON + dashboard JSON/CSV) are in repo.

---

## Automated checks (repo)

| Area | Count | Command / location |
|------|-------|---------------------|
| Backend | **160** tests (`pytest` **green** with PostgreSQL; DB URL coercion, write protection + meta routes; **`phase_latency_distribution`** (retrieval + **total** latency); dashboard **`scale`** + **retrieval** + **end-to-end** sec fields; **`no_database_cleanup`** marker for pure dataset-file tests; fake embedder in `tests/conftest.py`) | `cd backend && pytest` |
| Frontend | **195** Vitest tests (routing, dashboard + **scale grid** + **dashboard chart helpers** + **cost trend column**, summary **retrieval P50/P95** + **end-to-end s**, **`formatLatencySec`**, **exportDownload**, **run diagnosis**, **run diff**, **retrieval source** + **`/documents/:id`**, **phase timeline**, **runs list filters**, **queue browser**) | `cd frontend && npm run test` |
| Frontend E2E | **14** Playwright tests (run-detail **11** + runs-list **1** + queue-browser **1** + dashboard **1**; requires `npx playwright install`) | `cd frontend && npx playwright test` |
| Redis (RQ) | pre-flight | `cd backend && python scripts/check_redis_for_rq.py` |

---

## Phase 5 exit

- [x] URL-based navigation for all views (`/benchmark`, `/runs`, `/queue`, `/runs/:runId`, `/compare`, `/dashboard`)
- [x] `/runs/:runId` deep link with API fetch
- [x] Invalid run ID handled (inline error)
- [x] Browser history (back/forward/refresh) works
- [x] Existing 38 tests unbroken
- [x] 7 new routing tests pass
- [x] Build + lint clean
- [x] PROJECT.md, DECISIONS.md, TASK.md, CURRENT_STATE.md updated

## Phase 6 exit

- [x] `GET /api/v1/runs/dashboard-analytics` returns time_series, latency_distribution, failure_analysis, config_insights (pytest / ASGI)
- [x] Backend schema + service + route + 3 tests
- [x] Frontend types + client + 4 panel components + format helpers + chart-scanability layer + Vitest (see **Automated checks**)
- [x] Dashboard tab panels covered in Vitest with **mocked** summary + analytics APIs (parallel fetch path exercised in tests)
- [x] **Live** validation (2026-03-21): backend **200** on **`/runs/dashboard-summary`** + **`/runs/dashboard-analytics`** (empty + populated DB); Vite **proxy** path verified; **`DashboardPanel`** loading/success/error/empty via **Vitest** + successful real JSON (headed browser optional)
- [x] Existing tests unbroken (160 backend, 195 frontend)
- [x] Build + lint clean
- [x] PROJECT.md, DECISIONS.md, TASK.md, CURRENT_STATE.md, **`docs/DEV_FULL_RUN_QUEUE.md` §8** updated
