# RAG Systems Retrieval Engineering v1 — Benchmark Results

## Overview

This benchmark evaluates how different chunking and retrieval configurations affect latency, context quality, and answer completeness in a Retrieval-Augmented Generation (RAG) pipeline.

The dataset was intentionally designed to expose common RAG failure modes such as:

- retrieval partial
- chunk fragmentation
- context truncation
- incomplete answers

All results below are derived from actual stored run traces in PostgreSQL. No synthetic or estimated metrics are used.

---

## Dataset

**Name:** `rag_systems_retrieval_engineering_v1`

- 8 documents (technical RAG + retrieval topics)
- 8 queries designed to require multi-chunk reasoning and expose failure cases
- Expected answers used for heuristic evaluation

---

## Configurations Tested

### Config A — baseline_fast_small

- chunk size: ~380 characters
- top_k: 3

### Config B — balanced_medium

- chunk size: ~720 characters
- top_k: 5

### Config C — context_heavy_large

- chunk size: ~1200 characters
- top_k: 7

Each configuration uses a scoped document ingestion strategy to isolate chunking effects.

---

## Results (Measured)

### baseline_fast_small

- Runs (completed): 16
- Avg retrieval latency: **235.0 ms**
- Avg total latency: **238.4 ms**
- Failure rate: **0.0%**
- Avg retrieval relevance: **0.5162**
- Avg context coverage: **0.6163**
- Avg completeness: **0.8135**

---

### balanced_medium

- Runs (completed): 16
- Avg retrieval latency: **9.8 ms**
- Avg total latency: **11.8 ms**
- Failure rate: **0.0%**
- Avg retrieval relevance: **0.4030**
- Avg context coverage: **0.6841**
- Avg completeness: **0.9808**

---

### context_heavy_large

- Runs (completed): 16
- Avg retrieval latency: **8.9 ms**
- Avg total latency: **10.8 ms**
- Failure rate: **0.0%**
- Avg retrieval relevance: **0.3108**
- Avg context coverage: **0.8039**
- Avg completeness: **1.0000**

---

## Observed Tradeoffs

### 1. Chunk size vs completeness

Larger chunk sizes (Config C) significantly improved:

- context coverage
- answer completeness

However, they reduced retrieval relevance, indicating broader but less targeted context.

### 2. Retrieval precision vs coverage

Smaller chunks with lower top_k (Config A):

- produced higher retrieval relevance
- but failed to capture full context
- resulting in lower completeness

### 3. Latency behavior

Config A showed significantly higher average latency due to:

- embedding/model warm-up effects
- smaller chunk retrieval overhead

Configs B and C were substantially faster and more stable.

### 4. Best overall configuration

Config B (balanced_medium) provided the best tradeoff:

- high completeness (~0.98)
- strong context coverage
- low latency (~11.8 ms total)

---

## Limitations

- Results are aggregated from stored benchmark runs (not isolated single-pass experiments)
- Heuristic evaluation mode only (no LLM judge in this run)
- cost_usd is not available in heuristic mode
- Latency includes local environment effects (model warm-up, DB load)

---

## Reproducibility

To reproduce:

```bash
docker compose up -d db
cd backend
alembic upgrade head

python scripts/seed_rag_systems_benchmark.py
python scripts/run_rag_systems_benchmark.py
python scripts/export_rag_systems_benchmark_summary.py
```

To refresh this document from the database, paste the stdout of `export_rag_systems_benchmark_summary.py` into the **Results (Measured)** section or keep that script’s Markdown alongside this narrative file.
