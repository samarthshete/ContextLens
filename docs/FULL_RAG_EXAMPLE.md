# Example: full RAG run (retrieval → generation → LLM judge)

This mirrors **`run_benchmark.py --eval-mode full`** but shows the **service calls** and expected DB state.

## Preconditions

- `alembic upgrade head` (includes **`generation_results`** and **`evaluation_results.groundedness`**).
- `CLAUDE_API_KEY` set for live Anthropic calls.
- Chunks in DB for your corpus; benchmark seed + query cases (e.g. via `seed_benchmark.py`).

## Sequence (Python / async session)

1. **Retrieval** — creates `runs` row, `retrieval_results`, `retrieval_latency_ms`, `status = retrieval_completed`.

```python
from app.services.benchmark_run import execute_retrieval_benchmark_run

run = await execute_retrieval_benchmark_run(
    session,
    query_case_id=qc_id,
    pipeline_config_id=pc_id,
    document_id=doc_id,
    commit=True,
)
```

2. **Generation** — Claude answer, `generation_results`, `generation_latency_ms`, `status = generation_completed`.

```python
from app.services.generation_phase import execute_generation_for_run

await execute_generation_for_run(session, run_id=run.id, commit=True)
```

3. **LLM judge + complete** — `evaluation_results` with `used_llm_judge=True`, scores, `failure_type`, optional `cost_usd`; `status = completed`.

```python
from app.services.full_rag_evaluation import execute_llm_judge_and_complete_run

await execute_llm_judge_and_complete_run(session, run_id=run.id, commit=True)
```

## One-shot CLI (same outcome)

```bash
cd backend
export CLAUDE_API_KEY=sk-ant-...
python scripts/seed_benchmark.py
python scripts/run_benchmark.py --eval-mode full
python scripts/generate_contextlens_metrics.py --format markdown
```

## Heuristic alternative (no API key)

```bash
python scripts/run_benchmark.py --eval-mode heuristic
```

`metadata_json.evaluator_type` is **`heuristic`** vs **`llm`** for filtering in analytics.

## Tests without API keys

`tests/test_full_rag_mocked.py` patches `generate_rag_answer` and `evaluate_with_llm_judge` to avoid network calls.

---

## Inspect a run (after benchmarks)

With the API running (`uvicorn app.main:app --reload`):

```bash
curl -s "http://127.0.0.1:8000/api/v1/runs/1" | python -m json.tool
```

Replace `1` with the `run_id` printed by `run_benchmark.py`. The response includes **evaluator_type**, retrieval hits, optional **generation**, **evaluation**, and timings.
