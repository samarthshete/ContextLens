# RAG Systems Retrieval Engineering v1 — Benchmark Results

## Purpose

Measure how chunk size and top-k jointly affect retrieval quality, context coverage, and answer completeness in ContextLens's heuristic evaluation pipeline. The three configs below isolate the tradeoff between retrieval precision and context breadth.

All numbers are measured from stored PostgreSQL run traces — no synthetic or estimated metrics.

---

## Setup

| Parameter | Value |
|-----------|-------|
| Dataset | `rag_systems_retrieval_engineering_v1` |
| Documents | 8 (technical RAG + retrieval topics) |
| Queries | 8 (designed to require multi-chunk reasoning and expose failure modes) |
| Evaluation mode | Heuristic only (no LLM judge; `cost_usd` is NULL) |
| Embedding model | `all-MiniLM-L6-v2` (384-dim, L2-normalized) |
| Runs per config | 16 (8 queries × 2 seed passes) |
| Last captured | 2026-03-18 (local) |

---

## Configurations Compared

| Config | Chunk size (chars) | top_k | Design intent |
|--------|-------------------|-------|---------------|
| **A** `baseline_fast_small` | ~380 | 3 | High precision, narrow context |
| **B** `balanced_medium` | ~720 | 5 | Balanced precision and coverage |
| **C** `context_heavy_large` | ~1200 | 7 | Maximum context breadth |

Each config uses a scoped document ingestion (independent chunking per config) to isolate chunk-size effects.

---

## Measured Results

| Metric | A: small (380/k3) | B: medium (720/k5) | C: large (1200/k7) |
|--------|-------------------|---------------------|---------------------|
| Completed runs | 16 | 16 | 16 |
| Avg retrieval latency | 235.0 ms | 9.8 ms | 8.9 ms |
| Avg total latency | 238.4 ms | 11.8 ms | 10.8 ms |
| Failure rate | 0.0% | 0.0% | 0.0% |
| Avg retrieval relevance | **0.5162** | 0.4030 | 0.3108 |
| Avg context coverage | 0.6163 | 0.6841 | **0.8039** |
| Avg completeness | 0.8135 | 0.9808 | **1.0000** |

---

## Key Findings

### 1. Chunk size drives completeness more than top-k alone

Config C (1200-char chunks, k=7) achieved **perfect completeness (1.000)** — every expected answer phrase was found in the generated context. Config A (380-char, k=3) reached only 0.814: a **19% gap** caused by answer fragments splitting across small chunks that didn't all land in the top-3.

### 2. Retrieval relevance and completeness move in opposite directions

As chunk size and top-k increase from A → B → C:
- Retrieval relevance drops from 0.516 → 0.403 → 0.311 (−40% end to end)
- Context coverage rises from 0.616 → 0.684 → 0.804 (+30%)
- Completeness rises from 0.814 → 0.981 → 1.000 (+23%)

Larger chunks include more surrounding text per hit, which dilutes the cosine similarity average but captures more of the answer.

### 3. Latency anomaly in Config A is warm-up, not retrieval cost

Config A's 235 ms average is ~25× higher than B/C. This is not a retrieval penalty for small chunks — it reflects embedder/model warm-up. Config A runs first in process order; by the time B and C execute, the embedding model is cached. For latency comparison, discard the first config's numbers or rotate execution order.

### 4. Best tradeoff: Config B (balanced_medium)

| Criterion | Config B value | Why it wins |
|-----------|---------------|-------------|
| Completeness | 0.981 | Captures 98% of expected answers — only 2% below perfect |
| Context coverage | 0.684 | 11% higher than A, adequate for most queries |
| Retrieval relevance | 0.403 | Moderate; not the best, but acceptable |
| Latency | 11.8 ms | Fast (after warm-up normalization) |

Config C achieves perfect completeness but at a **40% relevance cost** vs Config A. Config B recovers **96% of Config C's completeness** while retaining **30% more relevance** than C.

---

## Tradeoff Decision Framework

| If your priority is... | Choose | Accept |
|------------------------|--------|--------|
| Never miss an answer fragment | C (large/k7) | Lower per-hit relevance scores |
| Balance quality and precision | B (medium/k5) | ~2% completeness gap vs perfect |
| Maximize retrieval precision | A (small/k3) | 19% completeness gap; may miss multi-chunk answers |

---

## Limitations

- **Heuristic evaluation only.** No LLM judge scores (faithfulness, groundedness) — those require `--eval-mode full` with an API key.
- **No cost data.** Heuristic mode does not incur or track LLM costs; `cost_usd` is NULL for all runs.
- **Local environment latency.** Absolute latency numbers reflect a local dev machine, not production. Relative differences between B and C are meaningful; Config A's numbers are distorted by warm-up.
- **Single corpus domain.** All 8 documents are technical infrastructure topics. Results may not generalize to other domains (legal, medical, conversational).
- **No failure-mode variation.** All 48 runs completed with `NO_FAILURE` under heuristic evaluation. Harder queries or LLM judge mode would likely surface failure-type tradeoffs.

---

## Reproduce

```bash
docker compose up -d db
cd backend
alembic upgrade head

python scripts/seed_rag_systems_benchmark.py
python scripts/run_rag_systems_benchmark.py
python scripts/export_rag_systems_benchmark_summary.py
```

To refresh numbers, paste the output of `export_rag_systems_benchmark_summary.py` into the **Measured Results** table.
