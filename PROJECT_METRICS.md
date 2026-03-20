# PROJECT METRICS

This file tracks only measured or directly computed project metrics.
Do not put guessed, aspirational, or resume-style numbers here.

Last updated: YYYY-MM-DD

---

Last updated: 2026-03-20

### Dataset / benchmark scale
- benchmark_datasets: 1
- total_queries: 3
- total_traced_runs: 6
- configs_tested: 2

### Performance (ms; from `runs` latency columns)
- avg_retrieval_latency_ms: 93.33
- p95_retrieval_latency_ms: 277.25
- avg_generation_latency_ms / p95_generation_latency_ms: not available (no measured samples)
- avg_evaluation_latency_ms: 2.33
- p95_evaluation_latency_ms: 3.75
- avg_total_latency_ms: 95.67
- p95_total_latency_ms: 280.25

### Quality / evaluation (from `evaluation_results`)
- average_faithfulness: not available
- average_completeness: 1.00
- average_retrieval_relevance_score: 0.337
- average_context_coverage_score: 0.40

### Failure types (counts)
- _no failure_type values stored — not available_

### Cost / efficiency
- avg_evaluation_cost_per_run_usd: not available
- llm_judge_call_rate: 0

### Ingestion inventory (optional)
- documents (ingestion): 1
- chunks (ingestion): 3

**Measurement notes**
- Metrics are generated from actual stored benchmark runs and evaluation rows.
- Current evaluation uses `minimal_retrieval_heuristic_v1`, not an LLM judge.
- `faithfulness`, `generation latency`, `evaluation cost`, and `failure_type` are not yet populated by the current benchmark workflow.
- `llm_judge_call_rate` is `0` because the current evaluator does not use an LLM judge.