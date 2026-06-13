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

When total runs exceed distinct query cases in the slice, `GET /runs/dashboard-summary` returns a `repeated_sampling_note` that names **unique query cases in the slice** vs **registered** `query_cases` inventory. The comparison panel still shows its own shorter “runs vs unique queries” line from config-comparison buckets.

## Latency Honesty

All latency figures in the dashboard and benchmark results are from **local runs** and are **directional only**. Cold-start, OS scheduler jitter, and model-cache warm-up can dominate early runs and inflate averages significantly. The UI:

- **Summary latency card:** order **median (P50) → P95 → mean** (mean visually de-emphasized); end-to-end includes **`total_latency_p50_ms`** / **`end_to_end_run_latency_p50_sec`** from the same population as total mean/P95.
- **Latency distribution panel:** **skew warning** (`role="alert"`) + fixed **median vs average** sentence when any phase has samples; per phase with **&lt;5** non-null timings → only *Insufficient samples for distribution (N runs)* (no percentile table/bars for that phase); **≥5** → bars + table with median before P95 before mean.
- **Badges** (when phase `count > 0`): **Low sample — not reliable** if count **&lt; 20**; **High variance (skewed distribution)** if **P95/median > 10** (constants in `frontend/src/benchmark/dashboardConstants.ts`).

Do not quote any latency number from a local run as a production-grade performance claim or SLA.

## Trace instrumentation (`runs.trace_instrumentation_json`)

After migration **0008**, completed runs may persist a JSON object with evaluator mode and **LLM judge** counters, for example:

- `evaluator_execution_mode`: `heuristic_only` | `llm_only` | `hybrid`
- `llm_judge_calls_attempted`, `llm_judge_calls_skipped_by_heuristics`, `llm_judge_calls_used_for_final_judgment`
- Optional token/cost estimates when the pipeline measured them

Values are written only from real code paths (heuristic completion, full LLM judge, or hybrid skip). Nothing is hardcoded for marketing.

## Hybrid judge gate

When `runs.metadata_json.evaluator_execution_mode == "hybrid"`, the worker may skip `evaluate_with_llm_judge` if `hybrid_retrieval_gate_passes(...)` is true (thresholds in `minimal_retrieval_evaluation.py`: max chunk score ≥ 0.88, mean relevance ≥ 0.55, context coverage ≥ 0.42). Skipped runs still have `generation_results` and store heuristic-style evaluation with `used_llm_judge=false` and explicit `hybrid_judge_skipped` metadata on the eval row.

## Diagnosis timing sessions

Table `diagnosis_timing_sessions` stores operator/researcher timing for **manual** vs **assisted** diagnosis. Metrics on the dashboard:

- `diagnosis_duration_sec` = `completed_at - started_at` (only sessions with `completed_at`)
- `time_to_first_insight_sec` = `first_meaningful_insight_at - started_at`

**Gating:** if either mode has **&lt;5** completed sessions, tier **insufficient**; **5–9** → **limited**; **≥10** both → **normal**. Rows with `synthetic=true` are excluded from dashboard aggregates.

### Diagnosis experiment candidate selection (balanced timing study)

Pure logic lives in `app/services/diagnosis_experiment_design.py` (unit-tested). **Buckets:** retrieval-related (`RETRIEVAL_*`, `CHUNK_FRAGMENTATION`), generation-incomplete (`ANSWER_*`, `CONTEXT_TRUNCATION`), mixed/ambiguous (`MIXED_FAILURE`, `UNKNOWN`, `CONTEXT_INSUFFICIENT`), easy control (`NO_FAILURE`); unknown labels map to mixed. **Scoring:** base +40 for non–easy-control; **NO_FAILURE penalty** (−50 default); **difficulty** from inverted eval subscores; **repeat-query penalty** when normalized query text (strip, lower, collapse whitespace) repeats (MD5 fingerprint); **session penalty** for existing non-synthetic sessions on the run. Sort **(−score, −run_id)**. **Plan:** 10 manual + 10 assisted slots; per mode targets **4 / 3 / 2 / 1** by bucket; greedy fill avoids duplicate `query_case_id` across groups when possible. **Warnings** when a bucket has fewer than **2 × target** candidates (cannot reserve diversity for both modes) or total planned slots &lt; 20. **`scripts/list_diagnosis_candidates.py`** prints `candidates` | `buckets` | `plan`; **`--export-plan`** writes CSV/JSON with stable column order (`EXPORT_PLAN_ROW_KEYS`).

## Matched LLM-judge reduction

Comparable **llm_only** vs **hybrid** runs must share `runs.metadata_json.matched_llm_reduction_workload_id` and use `matched_llm_reduction_arm` ∈ {`llm_only`, `hybrid`}. Per-workload reduction:

\[
\text{llm\_judge\_reduction\_pct} = \frac{\overline{\text{calls}}_{\text{llm\_only}} - \overline{\text{calls}}_{\text{hybrid}}}{\overline{\text{calls}}_{\text{llm\_only}}} \times 100
\]

where \(\overline{\text{calls}}\) is the mean of `llm_judge_calls_used_for_final_judgment` from `trace_instrumentation_json` on runs that also have `generation_results` and `evaluation_results`.

**Gating (dashboard):** let \(N = \min(\text{total llm\_only runs}, \text{total hybrid runs})\) across matched workloads. **N &lt; 3** → tier **sparse**; **3–9** → **directional**; **≥10** → **normal**.

## Evidence orchestration (2026-03-24)

Three scripts eliminate friction for generating the three core evidence types:

1. **Scale evidence** (`scripts/run_scale_evidence_pipeline.py`): One command seeds the 52-query benchmark, executes 208 traced runs (52 queries × 2 configs × 2 reps default), and verifies dashboard counts match expectations. `--force-recreate` deletes an invalid dataset and rebuilds. `--strict` fails on any verification mismatch.

2. **LLM reduction evidence** (`scripts/run_llm_reduction_evidence.py`): Automates matched workload generation — creates N workloads, runs both `llm_only` and `hybrid` arms per workload, then queries `build_llm_reduction_evidence()` for the current tier and reduction percentage. Requires `OPENAI_API_KEY` or `CLAUDE_API_KEY`. `--dry-run` validates without execution.

3. **Diagnosis timing DX** (`scripts/list_diagnosis_candidates.py`): Loads completed runs with evaluations → `score_candidates` → optional `build_experiment_plan`. Views: ranked **candidates**, **buckets** (pool size vs 2× per-bucket targets), **plan** (20 slots + warnings). `--export-plan` (CSV/JSON), `--export-sessions` (completed sessions + tier summary). Human interaction still required for actual timed sessions.

**Docker test support:** `Dockerfile` installs `.[dev]` (includes `pytest-asyncio`) and copies `tests/` directory so all **290** backend tests run inside the container.
