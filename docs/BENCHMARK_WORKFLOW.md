# Benchmark workflow — seed, run, metrics

This path produces **real database rows** (runs, retrieval results, optional generation, evaluation) so
`PROJECT_METRICS.md` can be generated from stored data only.

---

## 1. Prerequisites

- PostgreSQL with pgvector, schema at Alembic head (`cd backend && alembic upgrade head`).
- Environment: `DATABASE_URL` / `.env` as in `backend/app/config.py`.
- Embedding model downloads on first run (sentence-transformers).
- **Full RAG mode:** **`OPENAI_API_KEY`** by default (**`LLM_PROVIDER=openai`**), or **`CLAUDE_API_KEY`** when **`LLM_PROVIDER=anthropic`**.
- **HTTP/UI `eval_mode=full`:** **Redis** + RQ worker on queue **`contextlens_full_run`** (see **`docs/DEV_FULL_RUN_QUEUE.md`**, `backend/README.md`, Docker Compose **`redis`** / **`worker`**). Heuristic-only HTTP runs do not require Redis.

---

## 2. Seed benchmark registry (no timings, no scores)

Creates **one dataset**, **three query cases** (with `expected_answer` text taken from the
shared corpus for lexical completeness), and **two pipeline configs** (`top_k=5` and `top_k=8`).
Safe to run repeatedly (idempotent).

```bash
cd backend
python scripts/seed_benchmark.py
```

**Alternative (HTTP):** create or adjust rows with **`POST`/`PATCH`** on **`/api/v1/datasets`**, **`/api/v1/query-cases`**, **`/api/v1/pipeline-configs`** (see §7). Use this when you want explicit IDs without re-running the seed script.

---

## 3. Ingest corpus and execute runs

The runner:

1. Ensures the same seed as above (unless `--skip-seed`).
2. Ensures a **processed** document titled `ContextLens quickstart corpus` with the built-in
   benchmark text (idempotent), **or** uses `--document-id` to scope retrieval to an existing doc.
3. For each `(query_case × pipeline_config)` pair, runs **real** vector retrieval and persists
   `retrieval_results` + `retrieval_latency_ms` → `runs.status = retrieval_completed`.

Then behavior depends on **`--eval-mode`**:

### 3a. Heuristic (default)

- Computes **`minimal_retrieval_heuristic_v1`** (no LLM).
- Persists `evaluation_results` with `evaluator_type: heuristic`, `used_llm_judge=false`, **`cost_usd` NULL**, **`faithfulness` NULL** (no stored answer).
- Sets `runs.status = completed`.
- **`total_latency_ms`** = measured retrieval + measured heuristic evaluation time (script).

```bash
cd backend
python scripts/run_benchmark.py
# same as: --eval-mode heuristic
```

### 3b. Full RAG (`--eval-mode full`)

- Calls **Claude** to generate an answer from retrieved chunks → row in **`generation_results`**,
  `generation_latency_ms`, `status = generation_completed`.
- Calls **Claude LLM judge** → scores (`faithfulness`, `completeness`, **`groundedness`**, …),
  **`failure_type`** from fixed taxonomy, `used_llm_judge=true`, optional **`cost_usd`**
  (token-based estimate when `anthropic_*_usd_per_million_tokens` > 0 in config).
- Sets `runs.status = completed`.
- **`total_latency_ms`** = retrieval + generation + judge (each phase measured).

```bash
cd backend
python scripts/run_benchmark.py --eval-mode full
```

Other flags:

```bash
python scripts/run_benchmark.py --skip-seed
python scripts/run_benchmark.py --document-id 123 --eval-mode full
```

**Manual / dev:** use `persist_evaluation_and_complete_run` with `prerequisite_status`:
`retrieval_completed` (heuristic) or `generation_completed` (after `execute_generation_for_run`).
See **`docs/FULL_RAG_EXAMPLE.md`** for a service-level walkthrough.

---

## 4. Regenerate metrics markdown

```bash
cd backend
python scripts/generate_contextlens_metrics.py --format markdown
```

Paste stdout into `PROJECT_METRICS.md` under **ContextLens (generated metrics)**, or redirect:

```bash
python scripts/generate_contextlens_metrics.py --format markdown > /tmp/contextlens_metrics.md
```

---

## 5. Metric semantics (aggregation)

These definitions match `app/metrics/aggregate.py` and the generated Markdown **Semantics** block.

**Evaluator bucket** (`app/domain/evaluator_bucket.py`):

- **LLM:** `used_llm_judge IS TRUE` OR `metadata_json->>'evaluator_type' = 'llm'`
- **Heuristic:** otherwise

| Metric | Definition |
|--------|------------|
| **total_traced_runs** | Runs with ≥1 `retrieval_results` AND ≥1 `evaluation_results` (any bucket). |
| **total_traced_runs_heuristic** / **total_traced_runs_llm** | Same, filtered by evaluation row bucket. |
| **evaluation_rows_*** | Count of `evaluation_results` rows per bucket. |
| **avg_*_heuristic** / **avg_*_llm** (scores) | `AVG(column)` within that bucket where non-NULL — **never blended**. |
| **failure_type_counts_heuristic** / **_llm** / **_all** | Per-bucket `GROUP BY`; **_all** is audit-only. |
| **avg_evaluation_cost_per_run_usd_heuristic** / **_llm** | `AVG(cost_usd)` within bucket where `cost_usd IS NOT NULL`. |
| **llm_judge_call_rate** | `COUNT(used_llm_judge IS TRUE) / COUNT(evaluation_results)` over **all** rows. |
| **Global** run latencies | `avg_*_latency_ms` over all runs with non-NULL column. **Split** evaluation/total: `avg_*_latency_ms_heuristic` / `_llm` (join `runs` ↔ `evaluation_results`). |

---

## 6. Related files

| Path | Role |
|------|------|
| `backend/app/domain/failure_taxonomy.py` | `FailureType`, `normalize_failure_type` |
| `backend/app/services/benchmark_seed.py` | Corpus text, seed helpers |
| `backend/app/services/benchmark_run.py` | `execute_retrieval_benchmark_run` |
| `backend/app/services/generation_phase.py` | `execute_generation_for_run` |
| `backend/app/services/rag_generation.py` | Claude RAG answer |
| `backend/app/services/llm_judge_evaluation.py` | Claude JSON judge |
| `backend/app/services/full_rag_evaluation.py` | Judge + `persist_evaluation` for full path |
| `backend/app/services/minimal_retrieval_evaluation.py` | Heuristic evaluator |
| `backend/app/services/evaluation_persistence.py` | Completes run + evaluation row |
| `backend/scripts/seed_benchmark.py` | CLI seed |
| `backend/scripts/run_benchmark.py` | CLI runner (`--eval-mode`) |
| `backend/scripts/generate_contextlens_metrics.py` | Markdown from DB (split evaluator sections) |
| `backend/app/api/runs.py` | `POST /runs`, `POST /runs/{id}/requeue`, `GET /runs/{id}/queue-status`, `GET /runs`, `GET /runs/config-comparison`, `GET /runs/{id}` |
| `backend/app/services/run_requeue.py` | Structural eligibility + re-enqueue onto `contextlens_full_run` |
| `backend/app/services/run_queue_status.py` | Read-only lock + RQ job inspection |
| `backend/app/queue/full_run.py` | Enqueue full benchmark (`contextlens_full_run`); `find_primary_job_for_run` |
| `backend/app/workers/full_run_worker.py` | RQ worker job + lock |
| `backend/scripts/check_redis_for_rq.py` | Pre-flight Redis PING for full runs |
| `docs/DEV_FULL_RUN_QUEUE.md` | Ops runbook: retries, restarts, E2E checklist |
| `backend/app/api/datasets.py` | `GET`/`POST`/`PATCH`/`DELETE` `/datasets`, `GET /datasets/{id}` |
| `backend/app/api/query_cases.py` | `GET`/`POST`/`PATCH`/`DELETE` `/query-cases`, `GET /query-cases/{id}` |
| `backend/app/api/pipeline_configs.py` | `GET`/`POST`/`PATCH`/`DELETE` `/pipeline-configs`, `GET /pipeline-configs/{id}` |
| `backend/app/services/dataset_write.py` | Dataset create/update |
| `backend/app/services/dataset_delete.py` | Dataset delete (**409** if query cases exist) |
| `backend/app/services/query_case_write.py` | Query case create/update (FK checks) |
| `backend/app/services/query_case_delete.py` | Query case delete (**409** if runs exist) |
| `backend/app/services/pipeline_config_write.py` | Pipeline config create/update |
| `backend/app/services/pipeline_config_delete.py` | Pipeline config delete (**409** if runs exist) |
| `docs/METRICS_INSTRUMENTATION.md` | Table/column reference |
| `docs/FULL_RAG_EXAMPLE.md` | Example full RAG sequence |

---

## 7. Registry discovery, run create, listing, & comparison (HTTP)

Use your API origin (e.g. **Docker Compose** publishes **`localhost:8000`**; local **`uvicorn --port 8002`** matches the **default Vite proxy** — see `frontend/.env.example` / root **README**).

```bash
API=http://localhost:8000/api/v1   # or http://localhost:8002/api/v1
```

**Discover IDs** (no SQL) for `POST /runs`:

```bash
curl -s "$API/datasets"
curl -s "$API/query-cases?dataset_id=1"
curl -s "$API/pipeline-configs"
```

**Benchmark UI:** on **Run benchmark**, use **Upload document** to call **`POST /documents`** (same multipart contract as `curl -F file=@...`); the document dropdown refreshes and selects the new id for **`document_id`** on **`POST /runs`**.

**Create / update registry rows** (optional; **201** on `POST`, **200** on `PATCH`):

```bash
# Dataset
curl -s -X POST "$API/datasets" -H "Content-Type: application/json" \
  -d '{"name":"My benchmark set","description":"HTTP-created"}'
curl -s -X PATCH "$API/datasets/1" -H "Content-Type: application/json" \
  -d '{"description":"Updated via PATCH"}'

# Query case (replace DATASET_ID)
curl -s -X POST "$API/query-cases" -H "Content-Type: application/json" \
  -d '{"dataset_id":DATASET_ID,"query_text":"What is in the corpus?","expected_answer":null}'

# Pipeline config (retrieval params only)
curl -s -X POST "$API/pipeline-configs" -H "Content-Type: application/json" \
  -d '{"name":"pc-http","embedding_model":"all-MiniLM-L6-v2","chunk_strategy":"fixed","chunk_size":256,"chunk_overlap":0,"top_k":5}'
```

Invalid **`dataset_id`** on query-case create/update returns **404**. **`chunk_overlap` > `chunk_size`** returns **422**.

**Delete registry rows** (only when safe — else **409**): **`DELETE /datasets/{id}`** (blocked if any query cases), **`DELETE /query-cases/{id}`** (blocked if any runs), **`DELETE /pipeline-configs/{id}`** (blocked if any runs). Success → **204**.

```bash
curl -s -o /dev/null -w "%{http_code}\n" -X DELETE "$API/datasets/99"
```

**Create a traced run** — **`eval_mode=heuristic`:** synchronous **201** (same idea as the CLI). **`eval_mode=full`:** **202** + `job_id`; requires **Redis** + **`rq worker contextlens_full_run`** (see `backend/README.md`); poll `GET /runs/{id}` for status.

```bash
curl -s -X POST "$API/runs" \
  -H "Content-Type: application/json" \
  -d '{"query_case_id":1,"pipeline_config_id":1,"eval_mode":"heuristic"}'
```

**Inspect queue / lock** (full runs hit Redis; heuristic returns `pipeline=heuristic` without Redis):

```bash
curl -s "$API/runs/42/queue-status"
```

**Re-enqueue a stuck full run** (same RQ queue as initial **`eval_mode=full`**; **202** + new **`job_id`** when accepted):

```bash
curl -s -X POST "$API/runs/42/requeue"
```

Scope retrieval to one uploaded document (like `run_benchmark.py --document-id`):

```bash
curl -s -X POST "$API/runs" \
  -H "Content-Type: application/json" \
  -d '{"query_case_id":1,"pipeline_config_id":1,"eval_mode":"heuristic","document_id":42}'
```

Use `"eval_mode":"full"` only with the active provider API key set (**`OPENAI_API_KEY`** by default).

**Web UI:** from `frontend/`, `npm run dev` → same-origin `/api/v1/...` via Vite proxy (**`BACKEND_PROXY_TARGET`**, default **:8002**). In-app **tabs** (no router): registry → **`POST /runs`** → runs list → detail → config comparison.

After benchmark runs, inspect rows without SQL:

**List runs** (newest first; optional filters):

```bash
curl -s "$API/runs?dataset_id=1&limit=20&offset=0"
curl -s "$API/runs?pipeline_config_id=2&evaluator_type=llm&status=completed"
```

**Compare pipeline configs** — default returns **separate** heuristic and LLM buckets (same definitions as metrics):

```bash
curl -s "$API/runs/config-comparison?pipeline_config_ids=1&pipeline_config_ids=2&evaluator_type=both"
```

**Single merged row per config** (all evaluator buckets combined):

```bash
curl -s "$API/runs/config-comparison?pipeline_config_ids=1&pipeline_config_ids=2&combine_evaluators=true"
```

**Heuristic-only or LLM-only** slice:

```bash
curl -s "$API/runs/config-comparison?pipeline_config_ids=1&evaluator_type=heuristic"
curl -s "$API/runs/config-comparison?pipeline_config_ids=1&evaluator_type=llm"
```
