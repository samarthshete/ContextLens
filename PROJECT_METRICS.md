# PROJECT METRICS

This file is for **measured** metrics only. Do not add guessed or resume-style numbers.

**Refresh the numeric snapshot** (requires DB + migrations + optional benchmark data):

```bash
cd backend
python scripts/generate_contextlens_metrics.py --format markdown
```

Paste or redirect stdout below (or commit the generator output when you want a frozen snapshot). The **semantics** below mirror `render_project_metrics_markdown()` so readers know how to read the report.

---

## ContextLens (generated metrics)

*Numbers: run the command above — not checked in as a fake benchmark.*

### Semantics (read first)

- **N/A vs zero:** **“not available”** in generated output means **undefined / omitted** (`None` / SQL `NULL`), **not** the number zero.
  - **Averages** (scores, latencies, cost averages): no contributing non-NULL rows → **not available** (never a fake `0` average).
  - **Counts** (`benchmark_datasets`, `evaluation_rows_*`, `configs_tested`, …): **`0` is a real count**.
  - **`llm_judge_call_rate`:** **not available** when there are **zero** `evaluation_results` rows (denominator 0). If rows exist and none used the LLM judge, the rate is **`0`**.
- **total_traced_runs:** runs with ≥1 `retrieval_results` AND ≥1 `evaluation_results`.
- **total_traced_runs_heuristic** / **total_traced_runs_llm:** same, filtered by evaluator bucket (`app/domain/evaluator_bucket.py`).
- **Score averages** (`avg_*_heuristic` / `avg_*_llm`): **never blended** across buckets.
- **`cost_usd` (stored):** full RAG = **generation + judge** estimates summed (`app/services/full_rag_evaluation.py`). **Pricing disabled** (both `ANTHROPIC_*_USD_PER_MILLION_TOKENS` ≤ 0) or unknown usage → **`cost_usd` NULL** (not a fabricated `0` from missing rates).
- **avg_evaluation_cost_per_run_usd_***:** `AVG(cost_usd)` in that bucket over **non-NULL** `cost_usd` only; all-NULL → **not available**.
- **Failure-type counts:** only non-empty `failure_type` values; an empty list means **no such values in that slice**, not necessarily “zero failures”.

### Dataset / benchmark scale

- *(Generator output: `benchmark_datasets`, `total_queries`, traced run counts, …)*

### Performance, quality, failure types, cost

- *(See generator sections: global vs split latencies, `avg_*_llm` / `avg_*_heuristic`, failure buckets, `avg_evaluation_cost_per_run_usd_*`, `llm_judge_call_rate`.)*

### Ingestion inventory (optional)

- *(Generator output: `document_count`, `chunk_count` when those tables exist.)*
