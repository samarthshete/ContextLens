# `rag_systems_retrieval_engineering_v1`

Eight markdown topics (vector DBs, embeddings/chunking, HNSW, RAG architecture, failures, evaluation, latency, prompts) and **8** query cases with grounded `expected_answer` strings in the corpus.

## Registry name

`rag_systems_retrieval_engineering_v1` (dataset row in PostgreSQL).

## Pipeline configs (three variants)

| Config | Ingest `chunk_size` / `overlap` | `top_k` |
|--------|-----------------------------------|--------|
| `baseline_fast_small` | 380 / 40 | 3 |
| `balanced_medium` | 720 / 80 | 5 |
| `context_heavy_large` | 1200 / 120 | 7 |

Each config has its **own** processed document (same combined text, different chunking).  
`metadata_json["scoped_document_id"]` on the pipeline row points at that document for runs.

## Commands

```bash
cd backend
python scripts/seed_rag_systems_benchmark.py
python scripts/run_rag_systems_benchmark.py
python scripts/export_rag_systems_benchmark_summary.py
```

**Full RAG** (generation + LLM judge) is not wired here; use `run_benchmark.py --eval-mode full` with explicit IDs if needed.

## Results artifact

See **`docs/benchmark_results_rag_systems_retrieval_engineering_v1.md`** for measured results; re-run `export_rag_systems_benchmark_summary.py` to refresh the numeric table from PostgreSQL.
