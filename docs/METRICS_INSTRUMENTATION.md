# ContextLens metrics — instrumentation

**Rule:** Numbers in `PROJECT_METRICS.md` (ContextLens section) must come from the database via `backend/scripts/generate_contextlens_metrics.py` — no hand-written benchmarks.

---

## 1. Tables and what they feed

| Table | Role | Metrics fed |
|-------|------|-------------|
| **datasets** | Benchmark dataset registry (`name`, `description`, `metadata_json`) | `benchmark_datasets` → `COUNT(*)` |
| **query_cases** | Queries (`query_text`, optional `expected_answer`, `metadata_json`) | `total_queries` → `COUNT(*)` |
| **pipeline_configs** | Frozen params (`embedding_model`, `chunk_strategy`, `chunk_size`, `chunk_overlap`, `top_k`, …) | `configs_tested` → `COUNT(DISTINCT pipeline_config_id)` on **runs** |
| **runs** | One execution per query case + config; stores **measured** latencies | `total_traced_runs`*, split counts*, global + per-evaluator latency stats* |
| **retrieval_results** | Retrieved chunks (rank + score) per run | Required for **total_traced_runs** (see below) |
| **generation_results** | Generated answer + model + token usage (1:1 `run_id`) | Not aggregated in the default metrics script (inventory / future use) |
| **evaluation_results** | One row per run (scores, failure, judge, cost, **groundedness**) | Per-evaluator **split** averages / failure counts / cost; `llm_judge_call_rate` (global) |
| **documents** / **chunks** | Ingestion only | Optional inventory lines in script output (not benchmark scale) |

\* **`total_traced_runs`** = runs with ≥1 `retrieval_results` and ≥1 `evaluation_results`. **`total_traced_runs_heuristic` / `total_traced_runs_llm`** use the same rule but filter the evaluation row by **evaluator bucket** (`app/domain/evaluator_bucket.py`). **`runs.status` is not used** in these counts. Score **AVGs are never blended** across buckets (`avg_*_heuristic` vs `avg_*_llm`). **`llm_judge_call_rate`** = `COUNT(used_llm_judge IS TRUE) / COUNT(*)`: **undefined (N/A)** when there are zero evaluation rows; **0** when rows exist but none used the judge. See generated Markdown “Semantics” and `docs/BENCHMARK_WORKFLOW.md` §5.

---

## 2. Column reference (measurement fields)

### `runs`

| Column | Use |
|--------|-----|
| `status` | Lifecycle: `pending` → `running` → `retrieval_completed` → *(optional)* `generation_completed` → `completed` (or `failed`); `completed` when evaluation is persisted. Inspect via **`GET /api/v1/runs/{id}`**. |
| `retrieval_latency_ms` | Measured retrieval phase |
| `generation_latency_ms` | Measured generation phase (full RAG only) |
| `evaluation_latency_ms` | Measured evaluation phase |
| `total_latency_ms` | Sum of measured phases as written by the pipeline (heuristic: retrieval + eval; full: retrieval + generation + judge) |
| `created_at` | Audit |

**Avg / p95:** computed only over rows where the corresponding `*_latency_ms` **IS NOT NULL**. If no such rows → **not available**.

### `retrieval_results`

| Column | Use |
|--------|-----|
| `run_id`, `chunk_id`, `rank`, `score` | Stored trace; **score** is the retrieval similarity you persisted |

### `evaluation_results`

| Column | Use |
|--------|-----|
| `faithfulness`, `completeness`, `retrieval_relevance`, `context_coverage`, `groundedness` | `AVG` over non-NULL only |
| `failure_type` | `GROUP BY` counts; values normalized to **`FailureType`** strings |
| `used_llm_judge` | Numerator for `llm_judge_call_rate` (see below) |
| `cost_usd` | Full RAG: persisted **generation + judge** USD estimate (`estimate_usd_from_tokens` per phase). **NULL** when both Anthropic rates ≤ 0 or token usage unknown — not a fabricated **0**. Heuristic runs usually **NULL**. Aggregates: `AVG(cost_usd)` over non-NULL only per bucket; all-NULL → **not available**. |
| `metadata_json` | e.g. `evaluator_type`: `heuristic` \| `llm`; not aggregated by default |
| `created_at` | Audit |

---

## 3. What is computable without benchmark data

After core metrics migrations (through **`0006`**: `generation_results`, `groundedness`) are applied:

- All **counts** can be computed (often **0**).
- **Avg / p95 latencies** → **not available** until runs exist with non-NULL latency columns.
- **Score averages**, **per-bucket cost averages**, **`llm_judge_call_rate`** → **not available** until `evaluation_results` rows exist (and for cost averages, at least one non-NULL `cost_usd` in that bucket). **`llm_judge_call_rate`** is also **not available** when the evaluation table is empty (denominator 0). Integer **counts** (e.g. `benchmark_datasets`, `evaluation_rows_*`) may be **0** honestly.

**Ingestion-only** deployments still get **document** / **chunk** inventory lines from the script.

**N/A vs zero (Markdown):** the generator prints **“not available”** for undefined averages and for **`llm_judge_call_rate`** with no rows; it prints **`0`** for a real zero judge rate or a real zero count.

---

## 4. What requires benchmark runs

To see non-trivial benchmark metrics you must:

1. Insert **datasets** and **query_cases**.
2. Insert **pipeline_configs**.
3. Insert **runs** (linking query case + config) and populate **latency** columns from the app when each phase completes.
4. Insert **retrieval_results** for each run that should count as “traced”.
5. Insert **evaluation_results** with scores, `failure_type`, `used_llm_judge`, and `cost_usd` when you have real measurements / billing data.

Until then, the script prints **not available** or **0** where appropriate — never invented latencies or scores.

---

## 5. Files

| Path | Role |
|------|------|
| `backend/app/models/dataset.py` | `Dataset` |
| `backend/app/models/query_case.py` | `QueryCase` |
| `backend/app/models/pipeline_config.py` | `PipelineConfig` |
| `backend/app/models/run.py` | `Run` |
| `backend/app/models/retrieval_result.py` | `RetrievalResult` |
| `backend/app/models/evaluation_result.py` | `EvaluationResult` |
| `backend/app/models/generation_result.py` | `GenerationResult` |
| `backend/alembic/versions/0004_metrics_schema_runs_eval.py` | Base trace tables |
| `backend/alembic/versions/0006_generation_results_groundedness.py` | Generation + groundedness |
| `backend/app/metrics/aggregate.py` | SQL aggregations from real DB rows only |
| `backend/app/services/evaluation_persistence.py` | Writes `evaluation_results` + `evaluation_latency_ms` / `total_latency_ms` / `status=completed` |
| `backend/scripts/seed_benchmark.py` | Idempotent dataset / query cases / pipeline configs |
| `backend/scripts/run_benchmark.py` | Retrieval + heuristic or **full RAG** (`--eval-mode`) |
| `backend/scripts/generate_contextlens_metrics.py` | Aggregate → Markdown (**split by evaluator**) |
| `backend/app/services/llm_judge_parse.py` | Safe judge JSON parse + warnings |
| `backend/app/api/runs.py` | `GET /runs/{run_id}` run detail |
| `docs/BENCHMARK_WORKFLOW.md` | End-to-end commands and aggregation semantics |

---

## 6. Commands

```bash
# Apply schema
cd backend
alembic upgrade head

# Produce traced runs (optional quickstart — see docs/BENCHMARK_WORKFLOW.md)
python scripts/seed_benchmark.py
python scripts/run_benchmark.py
python scripts/run_benchmark.py --eval-mode full

# After benchmark jobs have written rows
python scripts/generate_contextlens_metrics.py --format markdown >> ../docs/contextlens_metrics_snippet.md
# Or paste stdout into PROJECT_METRICS.md under ## ContextLens
```

Optional: `--format text` for JSON-ish debug dump.

---

## 7. Out of scope (this schema)

- **AgentShield** metrics — separate project.
- **Human agreement** on failure labels — needs an extra column or table (not in minimal schema).
- **Productivity / time-study** lines in `PROJECT_METRICS.md` — not derived from these tables.
