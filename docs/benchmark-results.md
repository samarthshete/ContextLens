# Evidence benchmark — measured results

This file summarizes **real** runs produced by the **`evidence_rag_technical_v1`** dataset (see `benchmark-datasets/evidence-rag-v1/`). No placeholder metrics: numbers below come from PostgreSQL trace tables after:

```bash
cd backend
python scripts/run_evidence_benchmark.py
python scripts/export_evidence_benchmark_summary.py
```

**Last captured run (local):** 2026-03-18 — heuristic evaluation only (`minimal_retrieval_heuristic_v1`), retrieval scoped to document **Evidence RAG v1 — combined technical corpus** (`document_id` varies per environment).

---

## Dataset (v1)

- **8** technical mini-documents (HTTP caching, Postgres WAL, OAuth2, gRPC vs REST, idempotency, TLS, HNSW, structured logging), combined into **one** ingested document with `chunk_size=384`, `chunk_overlap=64`.
- **8** query cases with `expected_answer` phrases **grounded in the corpus** (`queries.json`).
- **3** pipeline configs differing primarily by **`top_k`**: `3`, `6`, `10` (see `EVIDENCE_PIPELINE_SPECS` in `app/services/benchmark_evidence_seed.py`).

---

## Per-config aggregates (completed runs)

_Source: `scripts/export_evidence_benchmark_summary.py` against the same DB session as below._

| Config | top_k | Runs | Avg retrieval latency (ms) | Avg total latency (ms) | Failure rate (≠ NO_FAILURE) | Avg retrieval_relevance |
|--------|-------|------|------------------------------|------------------------|-------------------------------|-------------------------|
| `evidence_topk3` | 3 | 8 | 61.9 | 64.6 | 0% | 0.5070 |
| `evidence_topk6` | 6 | 8 | 8.2 | 9.6 | 0% | 0.3781 |
| `evidence_topk10` | 10 | 8 | 8.2 | 9.6 | 0% | 0.2960 |

---

## Observed tradeoffs (this run)

1. **Retrieval relevance (heuristic):** **Decreases** as `top_k` increases (0.507 → 0.378 → 0.296). The heuristic averages over more hits; including lower-similarity chunks **dilutes** the aggregate relevance score even when recall is broader.
2. **Retrieval latency:** **`evidence_topk3` shows much higher average latency** in this capture than `top_k=6/10`. Per-run logs include **73–227 ms** for the first queries while later configs cluster around **7–13 ms** — consistent with **embedder/model warm-up** on the first batch (same process order: all queries for `top_k=3` first). For apples-to-apples latency, re-run after warm-up or rotate config order.
3. **Failures:** All **8×3** runs completed with **NO_FAILURE** under the heuristic for this corpus; failure-type tradeoffs would show up on harder queries or with **full** LLM judge (`run_benchmark.py --eval-mode full` on selected IDs).

---

## Reproducibility

| Artifact | Location |
|----------|----------|
| Corpus + queries | `benchmark-datasets/evidence-rag-v1/` |
| Seed service | `backend/app/services/benchmark_evidence_seed.py` |
| Scripts | `backend/scripts/seed_evidence_benchmark.py`, `run_evidence_benchmark.py`, `export_evidence_benchmark_summary.py` |
| Dashboard | Uses existing `GET /runs/dashboard-summary` and `GET /runs/dashboard-analytics` — populated when this DB contains these runs. |

Update this document after re-execution by pasting the output of `export_evidence_benchmark_summary.py` and refreshing the table.
