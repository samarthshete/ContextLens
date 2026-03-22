# Evidence RAG benchmark dataset (v1)

**Purpose:** Non-trivial, text-based corpus plus **8** query cases with `expected_answer` phrases grounded **verbatim** in the corpus. Used to produce **real** traced runs (retrieval + heuristic evaluation) and comparable pipeline configs.

## Contents

| Path | Role |
|------|------|
| `manifest.json` | Ordered list of corpus markdown files |
| `queries.json` | `query_text` + `expected_answer` per row |
| `corpus/*.md` | Eight standalone technical mini-docs |

## Pipeline configs (registry)

Created idempotently by the seed service (see `backend/app/services/benchmark_evidence_seed.py`):

| Config name | `top_k` | `chunk_size` (metadata) |
|-------------|---------|-------------------------|
| `evidence_topk3` | 3 | 256 |
| `evidence_topk6` | 6 | 384 |
| `evidence_topk10` | 10 | 512 |

**Ingest note:** The combined corpus is ingested **once** with fixed chunking (`chunk_size=384`, `chunk_overlap=64`, strategy `fixed`). Retrieval uses each config’s **`top_k`** at query time; differing `chunk_size` on the pipeline row documents the **experimental design** and matches a future workflow where operators re-ingest with that chunk size for apples-to-apples chunk ablations.

## Reproduce (heuristic, real DB traces)

From repo root, with PostgreSQL + schema migrated and `DATABASE_URL` set (see `backend/.env`):

```bash
cd backend
python scripts/run_evidence_benchmark.py
```

Seed only:

```bash
cd backend
python scripts/seed_evidence_benchmark.py
```

Summarize latest runs for this dataset (after benchmark):

```bash
cd backend
python scripts/export_evidence_benchmark_summary.py
```

Regenerate global metrics markdown (all datasets in DB):

```bash
cd backend
python scripts/generate_contextlens_metrics.py --format markdown
```

**Full RAG** (`generation` + LLM judge) is not wired in `run_evidence_benchmark.py`; use the generic `run_benchmark.py --eval-mode full` with appropriate IDs if you need judge scores and `cost_usd`.

## Versioning

- Dataset registry name: `evidence_rag_technical_v1`
- Combined document title: `Evidence RAG v1 — combined technical corpus`
- Bump `manifest.json` `version` and this README when the corpus or queries change materially.
