# CURRENT TASK

## Phase
**Phase 6 — Dashboard analytics (done). Run detail diagnosis + run diff + retrieval source labels + phase timeline (done in repo).**

---

## Objective (Phase 6 — completed)

Richer analytics layer for the Dashboard tab: time series, latency distributions, failure breakdown, and per-config insights — all from `GET /api/v1/runs/dashboard-analytics`.

## Objective (run detail diagnosis — v1 shipped)

Turn **`/runs/:runId`** into a clearer debugging surface using **existing** run-detail JSON only (no new backend contract for this slice). Optional UX polish remains (see **Next task**).

---

## Completed (concise)

- Everything from Phase 5 (see `CURRENT_STATE.md`)
- **Backend:**
  - Schema: `app/schemas/dashboard_analytics.py` (TimeSeriesDay, LatencyDistribution, FailureByConfig, ConfigInsight, etc.)
  - Service: `app/services/dashboard_analytics.py` — 4 async query functions (time series 90d, latency distribution with **`phase_latency_distribution.get_phase_latency_distribution`** + **`percentile_cont`**, failure analysis, config insights)
  - **`GET /runs/dashboard-summary`:** **`scale`** — **`benchmark_datasets`**, **`total_queries`**, **`total_traced_runs`**, **`configs_tested`**, **`documents_processed`**, **`chunks_indexed`** (definitions in **`DECISIONS.md`**; **`dashboard_summary.py`**; **`test_dashboard_summary_api.py`** shape + monotonic delta with traced run + corpus seed)
  - **`GET /runs/dashboard-summary`:** **`latency.retrieval_latency_p50_ms`** / **`retrieval_latency_p95_ms`** from same shared module (non-null **`runs.retrieval_latency_ms`** only; **`null`** if no samples) — **`dashboard_summary.py`** + **`test_dashboard_summary_api.py`**
  - **`GET /runs/dashboard-summary`:** **`latency.end_to_end_run_latency_avg_sec`** / **`end_to_end_run_latency_p95_sec`** from **`runs.total_latency_ms`** (same **`phase_latency_distribution`** query as **`avg_total_latency_ms`**; seconds = ms ÷ 1000)
  - **`GET /runs/dashboard-analytics`:** top-level **`end_to_end_run_latency_avg_sec`** / **`end_to_end_run_latency_p95_sec`** = **`latency_distribution.total`** avg/p95 ÷ 1000 (no extra SQL)
  - Route: `GET /api/v1/runs/dashboard-analytics` in `api/runs.py`
  - **3 new tests** (`test_dashboard_analytics_api.py`) + **3** (`test_phase_latency_distribution.py` — includes **`total_latency_ms`** distribution)
  - **168** total backend tests (all green with PostgreSQL; includes **`test_dashboard_summary_api.py`** per-run LLM/full-RAG cost + **`test_config_comparison_scores.py`** + extended **`test_runs_api`** for **`score_comparison_*`**; **`test_database_url_normalization.py`**, **`test_write_protection_api.py`**, **`test_evidence_dataset_load.py`**, **`test_rag_systems_dataset_load.py`**; **`no_database_cleanup`** marker for file-only checks)
- **Frontend:**
  - Types added to `api/types.ts`; `dashboardAnalytics()` method in `api/client.ts`
  - 4 new panel components: `DashboardTrendPanel`, `LatencyDistributionPanel`, `FailureBreakdownPanel`, `ConfigInsightsPanel`
  - Format helpers: `dashboardAnalyticsFormat.ts` (includes chart/stack/bar helpers for trends, latency, failures, config row emphasis)
  - `DashboardPanel` fetches summary + analytics in parallel via `Promise.all`
  - **`dashboardAnalyticsFormat.test.ts`** + **`dashboardFormat.test.ts`** + **`DashboardPanel.test.tsx`** cover helpers + panel chart/table expectations (trends `dashboard-trends-chart`, `failure-overall-bars`, config **attention** rows; **`dashboard-system-scale`**; summary **Latency** retrieval Mean/P50/P95; **End-to-end (total)** mean ms + avg/p95 s; **`formatLatencySec`**)
  - Updated mocks in `DashboardPanel.test.tsx` and `routing.test.tsx`
  - **199** total frontend Vitest tests (all green); **Dashboard cost per LLM / full-RAG run** + **Config comparison score spread** (**`scoreComparisonDisplay.tsx`**, **`scoreComparisonFormat.ts`**, **`configComparisonMock.ts`**, **`/compare`** + dashboard snapshot); **Config Insights** + **Run diff** + **retrieval source** + **`/documents/:documentId`** (document detail + linked hit sources) + **phase timeline** + **run diagnosis heuristic tuning** + **Recent runs search/filter** + **Queue browser** (`/queue`, **`queueBrowserLoad`**, **`QueueBrowserPanel`**, **`queueOperatorState`**, Vitest + **`e2e/queue-browser.spec.ts`**) + **dashboard** Playwright smoke **`e2e/dashboard.spec.ts`** + **export** helpers **`exportDownload`**
  - Build + lint clean
- **Run detail diagnosis (no new API):** `runDiagnosis.ts` (heuristic tuning as above) + **`RetrievalDiagnosisPanel`**, **`ContextQualityPanel`**, **`GenerationJudgeInsightsPanel`**, **`RunDiagnosisSummary`** in **`BenchmarkWorkspace`**; **`runDiagnosis.test.ts`** + routing **`run-diagnosis-summary`**
- **Run diff v1 (no new API):** **`runDiff.ts`** (`buildRunDiffModel`, reuses **`computeRetrievalDiagnosis`** / **`computeContextQuality`** / **`extractGenerationJudgeInsights`**) + **`RunDiffPanel`** on run detail (compare run ID input + **`api.getRun`**) + **`runDiff.test.ts`** + **`RunDiffPanel.test.tsx`**
- **Phase timeline (no new API):** **`runTimeline.ts`** (`buildTimelineModel` — phase durations, percentages when valid, dominant phase, summary) + **`PhaseTimeline`** component (proportional bars, duration, pct) mounted after Summary in run detail; replaces flat latency text. **`runTimeline.test.ts`** (11 tests) + **`PhaseTimeline.test.tsx`** (4 tests).
- **E2E regression tests (Playwright):** `e2e/run-detail.spec.ts` — **11** tests; **`e2e/runs-list.spec.ts`** — **1**; **`e2e/queue-browser.spec.ts`** — **1**; **`e2e/dashboard.spec.ts`** — **1**. Uses `page.route()` API mocking. Requires **`npx playwright install`** for local browser binaries.
- **Ops triage:** **`GET /api/v1/runs/dashboard-analytics` → 404** while **`dashboard-summary` → 200** ⇒ **stale backend process** — **`docker compose restart backend`** (see **`CURRENT_STATE.md`** limitations). Route is **`@router.get("/dashboard-analytics")`** in **`api/runs.py`**; not a separate path.

---

## Evidence benchmark (repo — executed)

- **Dataset:** `benchmark-datasets/evidence-rag-v1/` — 8 markdown topics, `queries.json`, `manifest.json`; registry name **`evidence_rag_technical_v1`**; 3 configs **`evidence_topk3` / `evidence_topk6` / `evidence_topk10`**.
- **Scripts:** `backend/scripts/seed_evidence_benchmark.py`, `run_evidence_benchmark.py`, `export_evidence_benchmark_summary.py`; service **`app/services/benchmark_evidence_seed.py`**.
- **Measured summary:** **`docs/benchmark-results.md`** (paste from `export_evidence_benchmark_summary.py` after each full run). Dashboard reflects data when runs exist in the connected DB.

### RAG systems retrieval engineering v1 (repo)

- **Dataset:** `backend/benchmark_data/rag_systems_retrieval_engineering_v1/` — 8 corpus files, `queries.json`, `manifest.json`; registry **`rag_systems_retrieval_engineering_v1`**.
- **Configs:** `baseline_fast_small` (ingest ~380 / `top_k` 3), `balanced_medium` (~720 / 5), `context_heavy_large` (~1200 / 7); each config scoped to its own ingested document via **`metadata_json.scoped_document_id`**.
- **Scripts:** `seed_rag_systems_benchmark.py`, `run_rag_systems_benchmark.py`, `export_rag_systems_benchmark_summary.py`; **`app/services/benchmark_rag_systems_seed.py`**.
- **Results doc:** **`docs/benchmark_results_rag_systems_retrieval_engineering_v1.md`** — measured results + tradeoffs from stored runs (regenerate via `export_rag_systems_benchmark_summary.py` as needed).

---

## Next task (primary)

**Deeper run-detail UX** (optional follow-ups): collapse raw JSON behind diagnosis, richer diff (e.g. answer text side-by-side).

**Deployment / hardening (done in repo):** **`docs/DEPLOYMENT.md`** (incl. **§9 Vercel + Render**), root **`render.yaml`**, **`CONTEXTLENS_WRITE_KEY`**, **`GET /api/v1/meta`**, **`WriteKeyBanner`**, **`APP_ENV=production`**, Docker **`alembic`** + **`rq_worker.sh`**, **`DATABASE_URL`** coercion for managed Postgres. ContextLens is **deployment-ready / production-like**, not enterprise SaaS — **you** run Blueprint/Vercel in your accounts to go live.

**Deeper queue / RQ admin** or **further dashboard visualization** — potential areas:
- Additional chart polish (e.g. cost over time) beyond **dashboard observability charts v1** (CSS/stacked bars; tables retained)
- Full RQ job browser / bulk queue ops (beyond **`/queue`** v1 + **`RunQueuePanel`**)

**Or:** operator-led **Phase 4 closure** if not yet done — `docs/DEV_FULL_RUN_QUEUE.md` §5 + §8 validation log per target environment.

### Shipped (dashboard — honest cost per run)

- **Backend:** **`DashboardCostSummary`** — **`avg_cost_usd_per_llm_run`**, **`llm_runs_with_measured_cost`**, **`avg_cost_usd_per_full_rag_run`**, **`full_rag_runs_with_measured_cost`**; **`dashboard_summary.py`** (LLM-bucket filter, **`SUM`/`GROUP BY run_id`** then **`AVG`**; full RAG = **`EXISTS generation_results`**); **`test_dashboard_summary_api.py`** (+ restored **`scale`** queries in **`get_dashboard_summary`**).
- **Frontend:** **`DashboardPanel`** cost copy + **`api/types.ts`**; **`exportDownload.ts`** CSV keys; Vitest **`DashboardPanel.test.tsx`**, **`exportDownload.test.ts`**, routing/runs mocks.

### Shipped (config-comparison decision metrics)

- **Backend:** `ConfigScoreComparisonSummary` + **`score_comparison`** / **`score_comparison_buckets`** on **`GET /runs/config-comparison`**; per-row **`avg_faithfulness`**; logic in **`app/services/config_comparison.py`**; schema **`app/schemas/config_comparison.py`**; tests **`test_config_comparison_scores.py`** (**`no_database_cleanup`**) + **`test_runs_api`**.
- **Frontend:** types in **`api/types.ts`**; **`scoreComparisonDisplay.tsx`** + **`scoreComparisonFormat.ts`**; dashboard **`CompareBucketsTable`**; **`/compare`** in **`BenchmarkWorkspace`** (columns + score cards); Vitest **`configComparisonMock.ts`**, **`scoreComparisonFormat.test.ts`**, **`DashboardPanel.test.tsx`**; routing/runs mocks include full comparison shape (inline — **`vi.mock` hoisting**).

### Shipped (export / reporting v1)

- Run detail **Export JSON** (`contextlens-run-{id}.json`) and Dashboard **Export JSON** / **Export CSV** (`contextlens-dashboard.json` / `contextlens-dashboard.csv`) from client-side payloads — **`exportDownload.ts`** + Vitest (**199** frontend tests; CSV **`summary_counts`** includes **`scale_*`** + **`cost_*_per_*_run`** keys + **`end_to_end_run_latency_*_sec`** + analytics sections).

### Shipped (queue / admin closure v1 — UI only)

- **`queueOperatorState.ts`** — operator badges from **`GET /runs/{id}/queue-status`** only (no new HTTP routes). **`QueueBrowserPanel`**: **Operator readout** column + recovery copy + requeue success notice + list reload after requeue. **`RunQueuePanel`**: matching summary block + clearer post-requeue hint.

---

## Backlog

- ~~Production deploy SPA fallback~~ — documented + `frontend/vercel.json`; nginx pattern in `docs/DEPLOYMENT.md`
- Full user auth / multi-user (beyond optional shared **`CONTEXTLENS_WRITE_KEY`**)
- Optional: heavier charting library or canvas/SVG-only panels if product needs it (v1 uses lightweight CSS bars)

---

## Done when (Phase 6)

- [x] `GET /api/v1/runs/dashboard-analytics` returns time_series, latency_distribution, failure_analysis, config_insights (automated tests)
- [x] Backend schema + service + route + tests
- [x] Frontend types + client + 4 panel components + format helpers
- [x] Dashboard tab: panels + parallel fetch path covered in Vitest (**mocked** APIs)
- [x] **Live** check (2026-03-21): real **`/runs/dashboard-summary`** + **`/runs/dashboard-analytics`** **200** (empty + populated); Vite proxy; **`DashboardPanel`** states covered by Vitest + real JSON (see **`CURRENT_STATE.md`**)
- [x] Frontend tests for format helpers
- [x] Existing tests unbroken
- [x] Build + lint clean
- [x] Docs updated (live validation logged)
