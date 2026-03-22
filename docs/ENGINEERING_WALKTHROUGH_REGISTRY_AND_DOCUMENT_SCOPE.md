# Engineering walkthrough: registry read APIs + optional `document_id` on `POST /runs`

**Audience:** You—the engineer who built (or maintains) ContextLens—and future you in interviews.  
**Scope:** The task that added (1) optional **`document_id`** on **`POST /api/v1/runs`**, and (2) **read-only HTTP APIs** for **datasets**, **query-cases**, and **pipeline-configs**.  
**Align with:** `PROJECT.md`, `DECISIONS.md`, `TASK.md`, `CURRENT_STATE.md`.

---

## 1. Big picture

### In simple words

Imagine your app is a **lab notebook** for RAG experiments. Before this task, you could **run an experiment from the API**, but the UI had to **guess magic numbers** (which dataset? which question? which config?) unless someone ran SQL or read seed scripts.

This task does two things:

1. **`document_id` on “start run”**  
   When you start a run, you can optionally say: *“only search inside **this** uploaded PDF.”*  
   If you omit it, behavior stays: *search **every** indexed chunk in the database*—same as before.

2. **“Phone book” APIs**  
   The UI can **list** datasets, questions (`query_cases`), and pipeline configs **over HTTP**, so it can show dropdowns and pass real integer IDs into `POST /runs` **without opening the database**.

### Why we built it

- **Product:** A real UI needs discoverable IDs and a way to scope retrieval to one corpus (demo, A/B on one doc).
- **Engineering:** Reuse existing benchmark code paths—**no second execution engine**. Validation is thin; execution stays in `execute_retrieval_benchmark_run` and friends.

### What new capability the project gains

| Capability | Before | After |
|------------|--------|--------|
| Know valid `query_case_id` / `pipeline_config_id` from the browser | SQL / seeds / guess | `GET /query-cases`, `GET /pipeline-configs`, `GET /datasets` |
| Scope benchmark retrieval to one document | CLI `--document-id` only | Same via JSON field `document_id` on `POST /runs` |
| Invalid document id | N/A (field didn’t exist) | Clean **404** before retrieval runs |

---

## 2. File-by-file walkthrough

Below: every **new** or **materially updated** file for this task. Tests and docs are included—you said don’t skip files.

---

### `backend/app/schemas/run_create.py` (updated)

**Why it exists**  
Defines the **contract** between HTTP clients and the run-creation endpoint: what JSON is allowed in and what JSON comes back.

**Problem it solves**  
Without Pydantic models, you’d parse dicts by hand and get inconsistent errors and types.

**Where it fits**  
**API layer input/output shapes**—not business logic.

**Responsibility**  
- Validate and document `RunCreateRequest` / `RunCreateResponse`.  
- **New in this task:** optional `document_id` (integer ≥ 1 or omitted/`null`).

**Main logic (step by step)**  
1. FastAPI reads JSON body into `RunCreateRequest`.  
2. Pydantic checks types: `query_case_id` and `pipeline_config_id` are ints ≥ 1; `eval_mode` is only `"heuristic"` or `"full"`; `document_id` is either missing/`null` or an int ≥ 1.  
3. If invalid → **422** (FastAPI default), not your custom handler.

**Inputs / outputs**  
- **In:** JSON body.  
- **Out:** Python objects used by `app/api/runs.py`.

**Connections**  
- Used by `app/api/runs.py` (`RunCreateRequest`, `RunCreateResponse`).  
- Field `document_id` is passed into `create_and_execute_run_from_ids`.

**Small example**  
```json
{
  "query_case_id": 3,
  "pipeline_config_id": 2,
  "eval_mode": "heuristic",
  "document_id": 14
}
```

**Interview one-liner**  
*“Run create uses Pydantic models so the API contract is explicit; we added an optional `document_id` that mirrors the retrieval API’s document filter.”*

---

### `backend/app/services/run_create.py` (updated)

**Why it exists**  
**Orchestrates** one full benchmark run in a single place so the HTTP route stays thin and the CLI could reuse the same function later if you wanted.

**Problem it solves**  
Without this service, route handlers would duplicate the multi-step flow (retrieval → eval or retrieval → generation → judge) and error handling.

**Where it fits**  
**Service layer**—between API and persistence / retrieval / LLM calls.

**Responsibility**  
1. Validate that **foreign keys exist** (`QueryCase`, `PipelineConfig`, and if provided **`Document`**).  
2. For `full` mode, ensure the active LLM provider key is configured (`require_llm_api_key_for_full_mode`).  
3. Call existing benchmark functions **in order**, with **`commit=False`** on inner steps, then **one `commit`** at the end.  
4. Return the final **`Run`** ORM object (refreshed).

**Main logic (step by step)**  
1. `session.get(QueryCase, query_case_id)` → missing → `QueryCaseNotFoundError`.  
2. `session.get(PipelineConfig, pipeline_config_id)` → missing → `PipelineConfigNotFoundError`.  
3. **If `document_id` is not `None`:** `session.get(Document, document_id)` → missing → `DocumentNotFoundError`. *(This runs **before** creating a run row—no orphan run.)*  
4. If `eval_mode == "full"`: `require_llm_api_key_for_full_mode()` → failure → `FullModeNotConfiguredError`.  
5. `execute_retrieval_benchmark_run(..., document_id=document_id, commit=False)` — creates run, runs `search_chunks` with that scope, stores retrieval rows, sets `retrieval_completed`.  
6. **Heuristic branch:** time `compute_minimal_retrieval_evaluation`, then `persist_evaluation_and_complete_run(..., commit=False)`.  
7. **Full branch:** `execute_generation_for_run`, then `execute_llm_judge_and_complete_run`, both `commit=False`.  
8. `await session.commit()` then `await session.refresh(run)`.

**Inputs / outputs**  
- **In:** `AsyncSession`, ids, `eval_mode`, optional `document_id`.  
- **Out:** persisted `Run` with `status` typically `"completed"`.

**Connections**  
- **Upstream:** `app/api/runs.py`.  
- **Downstream:** `benchmark_run`, `minimal_retrieval_evaluation`, `evaluation_persistence`, `generation_phase`, `full_rag_evaluation`, `anthropic_client`.  
- **Models:** `Document`, `QueryCase`, `PipelineConfig`, `Run`.

**Small example**  
UI sends `document_id: 5`. Service checks row 5 exists in `documents`, then retrieval only considers chunks belonging to document 5 (same semantics as `POST /retrieval/search` with `document_id`).

**Interview one-liner**  
*“Run creation is a thin orchestrator: validate FKs and optional document, then delegate to the same functions the benchmark CLI uses, with a single transaction commit at the end.”*

---

### `backend/app/api/runs.py` (updated)

**Why it exists**  
HTTP adapter for everything under **`/api/v1/runs`**: list, create, config comparison, detail.

**Problem it solves**  
Maps **HTTP concerns** (status codes, JSON) to **Python exceptions** and **service calls**.

**Where it fits**  
**FastAPI router**—transport layer.

**Responsibility**  
- **`POST ""`:** Parse body as `RunCreateRequest`, call `create_and_execute_run_from_ids`, map exceptions to HTTP errors, return `RunCreateResponse`.  
- **New:** pass `body.document_id`; catch `DocumentNotFoundError` → **404** `"Document not found."`

**Main logic for POST (step by step)**  
1. Dependency injects `AsyncSession` (`get_db`).  
2. `try: create_and_execute_run_from_ids(..., document_id=body.document_id)`.  
3. `QueryCaseNotFoundError` → 404 query case.  
4. `PipelineConfigNotFoundError` → 404 pipeline config.  
5. `DocumentNotFoundError` → 404 document.  
6. `FullModeNotConfiguredError` → **503** (service unavailable / misconfiguration).  
7. `anthropic.APIError` → **502** (bad gateway / upstream).  
8. Success → **201** + `{ run_id, status, eval_mode }`.

**Inputs / outputs**  
- **In:** HTTP request JSON.  
- **Out:** HTTP JSON + status.

**Connections**  
- `schemas/run_create.py`, `services/run_create.py`, `database.get_db`.

**Interview one-liner**  
*“The route stays dumb: translate service exceptions to HTTP status codes so the service layer stays framework-agnostic.”*

---

### `backend/app/schemas/dataset_read.py` (new)

**Why it exists**  
Public **read shape** for dataset rows—what the API is allowed to expose.

**Problem it solves**  
Avoid returning raw ORM objects with accidental fields; keep responses stable for the UI.

**Responsibility**  
`DatasetRead`: `id`, `name`, `description`, `created_at` with `from_attributes=True` so you can build from SQLAlchemy models.

**Connections**  
`app/api/datasets.py` uses `DatasetRead.model_validate(row)`.

**Interview line**  
*“Separate read DTOs so we don’t leak internal columns or JSON blobs we didn’t intend.”*

---

### `backend/app/schemas/query_case_read.py` (new)

**Same pattern as datasets.**  
Exposes `id`, `dataset_id`, `query_text`, `expected_answer`, `metadata_json` for dropdowns and run creation.

**Interview note**  
`expected_answer` is optional in DB; UI can show “reference answer” for judges or gold comparison.

---

### `backend/app/schemas/pipeline_config_read.py` (new)

**Same pattern.**  
Exposes retrieval parameters: `embedding_model`, `chunk_strategy`, `chunk_size`, `chunk_overlap`, `top_k`, `name`, `created_at`.

**Honest note**  
There is **no** “heuristic vs full” flag on `pipeline_configs` in the schema—that’s chosen **per run** in `RunCreateRequest.eval_mode`. The docstring in the file says this explicitly.

---

### `backend/app/services/dataset_list.py` (new)

**Why it exists**  
Encapsulate **how** we query datasets so the API file doesn’t embed SQL.

**Responsibility**  
- `list_datasets`: `SELECT * FROM datasets ORDER BY created_at DESC, id DESC` (newest first, stable tie-break).  
- `get_dataset_by_id`: primary key lookup.

**Connections**  
`app/models/dataset.py` (`Dataset` ORM).

**Interview line**  
*“Read services are boring on purpose: one query, one ordering rule, easy to test.”*

---

### `backend/app/services/query_case_list.py` (new)

**Why it exists**  
List query cases with optional **dataset filter**, with explicit semantics when the filter is invalid.

**Responsibility**  
1. If `dataset_id` is passed: load `Dataset`; if missing → raise **`DatasetNotFoundForFilterError`** (not an empty list—caller maps to 404).  
2. Build `select(QueryCase)` with optional `WHERE dataset_id = ?`.  
3. Order by `dataset_id`, then `id` ascending (stable, predictable for UI).

**Design choice (be ready to defend)**  
**404 vs empty list** for bad `dataset_id`: we chose **404** so a typo doesn’t look like “this dataset has zero questions.”

**Connections**  
`Dataset`, `QueryCase` models; `app/api/query_cases.py` catches `DatasetNotFoundForFilterError`.

---

### `backend/app/services/pipeline_config_list.py` (new)

**Responsibility**  
List all configs ordered by **`id` ascending** (deterministic); get by id.

**Connections**  
`PipelineConfig` model.

---

### `backend/app/api/datasets.py` (new)

**Why it exists**  
Expose **`GET /datasets`** and **`GET /datasets/{id}`** under the main API router.

**Responsibility**  
- List: call `list_datasets`, map each row to `DatasetRead`.  
- Detail: `get_dataset_by_id`; `None` → **404**.

**Connections**  
`get_db`, `dataset_list` service, `DatasetRead` schema.

---

### `backend/app/api/query_cases.py` (new)

**Responsibility**  
- **`GET /query-cases`:** optional query param `dataset_id`; on `DatasetNotFoundForFilterError` → **404**.  
- **`GET /query-cases/{id}`:** 404 if missing.

**Connections**  
`query_case_list` service, `QueryCaseRead` schema.

---

### `backend/app/api/pipeline_configs.py` (new)

**Responsibility**  
List + get by id; 404 on missing config.

---

### `backend/app/api/__init__.py` (updated)

**Why it changed**  
Mount new routers on the shared `APIRouter` with prefixes:

- `/datasets`  
- `/query-cases`  
- `/pipeline-configs`  

**Order note**  
`runs` stays last among these only matters relative to **other** apps; there’s no path collision between `/datasets` and `/runs`.

**Interview line**  
*“Single `api` package aggregates routers; `main.py` mounts one prefix `/api/v1`.”*

---

### `backend/tests/test_run_create_api.py` (updated)

**Why it exists**  
Prove `POST /runs` behavior end-to-end against the real app + DB.

**New tests (this task)**  
1. **`test_create_run_heuristic_with_document_id_success`**  
   Upload two documents (RAG text vs unrelated text), create qc+pc, POST with `document_id` pointing at the RAG doc, then `GET /runs/{id}` and assert **every retrieval hit’s `document_id`** matches—proves scoping.  
2. **`test_create_run_invalid_document_id_returns_404`**  
   Valid qc+pc but `document_id: 999999` → **404** and detail mentions document.

---

### `backend/tests/test_datasets_api.py` (new)

**Covers**  
List ordering (newer before older when both exist in response), get by id, 404 for missing id.

---

### `backend/tests/test_query_cases_api.py` (new)

**Covers**  
Filter by `dataset_id` returns only those rows; unknown `dataset_id` → **404**; unfiltered list works; get by id + 404.

---

### `backend/tests/test_pipeline_configs_api.py` (new)

**Covers**  
List contains seeded fields; get by id; 404.

---

### `docs/BENCHMARK_WORKFLOW.md` (updated)

**Why**  
Operators need curl examples for registry discovery and `document_id` on `POST /runs`.

**Not “code”** but part of the **deliverable** for this task—treat it as user-facing spec for the same behavior.

---

### `PROJECT.md`, `DECISIONS.md`, `TASK.md`, `CURRENT_STATE.md` (updated)

These record **what exists** and **what doesn’t** (e.g. read APIs yes, CRUD no). Section 8 below summarizes required alignment.

---

## 3. End-to-end flow

### A) UI discovers IDs, then starts a scoped heuristic run

**Simple language**  
1. Browser asks: “What datasets exist?”  
2. User picks one; browser asks: “What questions belong to that dataset?”  
3. Browser asks: “What pipeline configs exist?”  
4. User picks an uploaded document id (from documents list—existing API).  
5. Browser POSTs “run this question with this config, only search this document.”  
6. Server checks everything exists, runs retrieval + heuristic scoring, saves rows, answers with run id.

**Technical trace (files)**  
1. `GET /api/v1/datasets` → `app/api/datasets.py` → `dataset_list.list_datasets` → DB → `DatasetRead` JSON.  
2. `GET /api/v1/query-cases?dataset_id=1` → `query_cases.py` → `query_case_list.list_query_cases` (validates dataset exists) → `QueryCaseRead[]`.  
3. `GET /api/v1/pipeline-configs` → `pipeline_config_list` → JSON.  
4. `POST /api/v1/runs` with body → `runs.py` `create_run_endpoint` → `RunCreateRequest` validation.  
5. `create_and_execute_run_from_ids` validates `Document` if `document_id` set.  
6. `execute_retrieval_benchmark_run` → `search_chunks(..., document_id=...)` → writes `runs`, `retrieval_results`.  
7. `compute_minimal_retrieval_evaluation` → `persist_evaluation_and_complete_run` → `evaluation_results`, `runs.status = completed`.  
8. `session.commit()` in service.  
9. Response `RunCreateResponse` built in route.

### B) Invalid `document_id`

**Simple language**  
Server checks the document **before** creating a run. You get 404 and **no** new run row.

**Technical**  
`run_create.py` lines 57–60 → `DocumentNotFoundError` → `runs.py` → HTTP 404.

---

## 4. Architecture and design reasoning

### Why this logic lives in these files

| Layer | Role |
|--------|------|
| **`schemas/*_read.py`** | Stable JSON contract for reads; Pydantic validation/coercion. |
| **`services/*_list.py`**, **`run_create.py`** | Reusable queries and orchestration; **no** FastAPI imports. |
| **`api/*.py`** | HTTP only: status codes, dependency injection, `response_model`. |

### Why separate service / API / schema

- **Testability:** You can test `list_query_cases` with a session fixture without spinning HTTP.  
- **Clarity:** Business rules (e.g. “bad dataset filter → error”) live in one place.  
- **DECISIONS.md alignment:** Writes that commit are explicit; `get_db` doesn’t auto-commit.

### Alternatives considered (implicitly)

1. **Put SQL inside route handlers** — faster to write, worse to test and reuse.  
2. **Return empty list for bad `dataset_id`** — simpler, but hides client bugs; we chose 404.  
3. **One giant `/registry` endpoint** — fewer routes, messier evolution; split resources match REST habits and UI caching.

### Why this is reasonable for ContextLens

The project already had **scripts** + **services** for benchmark execution. This task **exposes** discovery and **threads** one optional parameter through—low risk, high leverage for a UI.

---

## 5. Risks and edge cases

### What can go wrong

| Risk | Detail |
|------|--------|
| **Long requests** | `POST /runs` full mode runs generation + judge **inline**; client timeouts, worker blocking. |
| **Document exists but has no chunks / not embedded** | Retrieval may return **empty** hits; heuristic eval still runs—valid but confusing UX. |
| **Concurrent writes** | Same session pattern as before; no new locking introduced. |
| **Large registry lists** | No pagination on `GET /datasets` etc.; fine for small benchmarks, weak at scale. |

### Handled failure cases

- Missing query case, pipeline config, document (when provided) → **404**.  
- Full mode without API key → **503** with message from `require_llm_api_key_for_full_mode`.  
- Anthropic errors on full path → **502**.  
- Malformed JSON / bad `eval_mode` → **422** (Pydantic).  
- Invalid `dataset_id` on query-case list → **404**.

### Still weak / debt

- **No pagination** on registry list endpoints.  
- **No write APIs** for datasets/query_cases/pipeline_configs—still seed/SQL for creating registry rows.  
- **`document_id` validates existence only**—not `status=processed` or “has embeddings.”  
- **Registry read tests** don’t assert global DB isolation beyond existing `cleanup_db`—rely on autouse cleanup.

### Anything poorly designed?

Not “wrong,” but **asymmetric**: you can **list** query cases but not **create** them via API yet—document that honestly in interviews as intentional scope control.

---

## 6. Interview preparation

### 60-second pitch

*“We made the benchmark runnable from a UI without SQL. I added optional `document_id` on `POST /runs` so retrieval is scoped to one uploaded document, reusing the same `search_chunks` path as the CLI. I also added read-only REST endpoints for datasets, query cases, and pipeline configs so the frontend can populate dropdowns with real integer foreign keys. Validation is layered: Pydantic for shape, service layer for FK and document existence before any run row is created, and the route maps domain exceptions to 404/502/503. Execution is still the existing benchmark stack—one transaction commit at the end.”*

### 10 questions, strong answers, follow-ups

**Q1: Why optional `document_id` instead of always requiring it?**  
**A:** Backward compatibility and parity with global semantic search: omitting it means “search the whole index,” which matches the previous default and `run_benchmark` without `--document-id`.

**Q2: Why 404 for a bad `dataset_id` filter instead of `[]`?**  
**A:** A missing dataset is a client error; returning 404 makes typos visible instead of silently looking like an empty dataset.

**Q3: Where is the actual retrieval scoped?**  
**A:** In `execute_retrieval_benchmark_run` → `search_chunks(..., document_id=...)`. We didn’t duplicate retrieval logic.

**Q4: Why custom exceptions instead of HTTPException in the service?**  
**A:** Keeps services independent of FastAPI; routes own HTTP mapping; easier unit testing.

**Q5: Single commit at the end—what if something fails mid-way?**  
**A:** SQLAlchemy session rolls back on error if nothing committed; inner steps use `commit=False` so the whole create+execute is atomic.

**Q6: How does this relate to “traced runs” and metrics?**  
**A:** Same tables (`runs`, `retrieval_results`, `evaluation_results`). Metrics and config-comparison aggregates still apply once the run completes.

**Q7: Why separate files per resource (datasets, query_cases, pipeline_configs)?**  
**A:** Clear ownership, smaller diffs, matches REST resources, avoids a god router.

**Q8: Security?**  
**A:** Project is single-user, no auth in scope (per PROJECT/DECISIONS)—honest limitation.

**Q9: Why Pydantic `model_validate` from ORM?**  
**A:** Explicit allowlist of fields for API responses; `from_attributes` bridges SQLAlchemy models safely.

**Q10: What would you add next?**  
**A:** Pagination for registry lists; optional POST for query cases; validate document `status` before run; async job queue for full RAG.

**Three likely deep follow-ups**

1. **“Walk me through SQLAlchemy async session and commits.”**  
   → `get_db` yields session; route doesn’t commit; `create_and_execute_run_from_ids` commits after success; rollback on exception.

2. **“How would you add pagination?”**  
   → `limit`/`offset` or cursor on list queries; wrap response in `{ items, total }` like `GET /runs`.

3. **“Idempotency for POST /runs?”**  
   → Today each POST creates a **new** run row—by design for experiments; idempotency keys would be a new feature.

---

## 7. Verification

### Local test commands

From repo root (with Postgres + pgvector as your project expects):

```bash
cd backend
# ensure deps + DB
.venv/bin/python -m pytest tests/ -q
```

### What success looks like

```
..............................           [100%]
NN passed in ...
```

(As of this walkthrough’s task, expect **58** passing tests if nothing else changed.)

### How you know it’s *correct*, not just green

1. **Scoped run:** `POST /runs` with `document_id` → `GET /runs/{id}` → all `retrieval_hits[].document_id` equal that id.  
2. **Bad document:** `POST /runs` with nonsense `document_id` → **404**, no new run.  
3. **Registry:** `GET /query-cases?dataset_id=<bad>` → **404**; good id → only rows for that dataset.

### Manual curl smoke (optional)

```bash
curl -s "http://localhost:8000/api/v1/datasets"
curl -s "http://localhost:8000/api/v1/query-cases?dataset_id=1"
curl -s "http://localhost:8000/api/v1/pipeline-configs"
curl -s -X POST "http://localhost:8000/api/v1/runs" \
  -H "Content-Type: application/json" \
  -d '{"query_case_id":1,"pipeline_config_id":1,"eval_mode":"heuristic","document_id":1}'
```

(Replace IDs with real ones from your DB.)

---

## 8. Documentation alignment

**If docs already reflect this task, no further change is required.** The following is what **must** stay true in the four source-of-truth files (verify on drift):

| File | What must be true for *this* task |
|------|-----------------------------------|
| **PROJECT.md** | Documents **`GET /datasets`**, **`GET /query-cases`** (+ filter), **`GET /pipeline-configs`**; **`POST /runs`** documents optional **`document_id`** and 404 for missing document; **not implemented** = registry **write** APIs (unless you add them later). |
| **DECISIONS.md** | **`POST /runs`** body includes optional `document_id` + validation; **benchmark registry read API** decision: read-only, 404 for bad `dataset_id` filter, eval mode is per-run not on `pipeline_configs`. |
| **TASK.md** | Completed items mention registry read APIs + `document_id`; **next** tasks point at UI wiring and optional write APIs / queue—not claiming CRUD is done. |
| **CURRENT_STATE.md** | Limitations: no HTTP CRUD for registry (if still true); **`POST /runs`** synchronous; test count matches CI. |

**`docs/BENCHMARK_WORKFLOW.md`:** Should include curl examples for registry discovery and `document_id` on `POST /runs` (operator path).

---

## Quick file checklist (nothing skipped)

| File | Role |
|------|------|
| `schemas/run_create.py` | Request/response + optional `document_id` |
| `services/run_create.py` | Orchestration + `DocumentNotFoundError` |
| `api/runs.py` | POST maps errors; passes `document_id` |
| `schemas/dataset_read.py` | Dataset JSON shape |
| `schemas/query_case_read.py` | Query case JSON shape |
| `schemas/pipeline_config_read.py` | Pipeline config JSON shape |
| `services/dataset_list.py` | Dataset queries |
| `services/query_case_list.py` | Query case queries + filter error |
| `services/pipeline_config_list.py` | Pipeline config queries |
| `api/datasets.py` | HTTP datasets |
| `api/query_cases.py` | HTTP query cases |
| `api/pipeline_configs.py` | HTTP pipeline configs |
| `api/__init__.py` | Router registration |
| `tests/test_run_create_api.py` | document_id success + 404 |
| `tests/test_datasets_api.py` | Datasets API |
| `tests/test_query_cases_api.py` | Query cases API |
| `tests/test_pipeline_configs_api.py` | Pipeline configs API |
| `docs/BENCHMARK_WORKFLOW.md` | Operator examples |
| `PROJECT.md`, `DECISIONS.md`, `TASK.md`, `CURRENT_STATE.md` | Truthful product state |

---

*End of walkthrough. Use this file when onboarding, reviewing, or preparing for interviews.*
