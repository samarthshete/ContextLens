# PROJECT METRICS

This file tracks only measured or directly computed project metrics.
Do not put guessed, aspirational, or resume-style numbers here.

Last updated: YYYY-MM-DD

---

## ContextLens

### Dataset / benchmark scale
- benchmark_datasets:
- total_queries:
- total_traced_runs:
- configs_tested:

### Quality / evaluation
- failure_categories_supported:
- classification_agreement:
- average_faithfulness_score:
- average_completeness_score:
- average_retrieval_relevance_score:
- average_context_coverage_score:

### Performance
- avg_retrieval_latency_ms:
- p95_retrieval_latency_ms:
- avg_evaluation_latency_ms:
- p95_evaluation_latency_ms:
- avg_end_to_end_latency_ms:

### Productivity / debugging
- debugging_time_before_minutes:
- debugging_time_after_minutes:
- average_time_to_compare_two_configs_minutes:

### Cost / efficiency
- avg_evaluation_cost_per_run_usd:
- llm_judge_call_rate:
- hybrid_cost_reduction_percent:

### Notable experiment findings
- best_chunking_strategy:
- best_config_by_faithfulness:
- largest_quality_improvement_found:
- largest_regression_detected:

---

## AgentShield

### Security coverage
- attack_categories:
- total_test_cases:
- workflows_or_configs_scanned:
- findings_total:
- findings_high_or_critical:

### Detection quality
- precision:
- recall:
- f1_score:
- false_positive_rate:
- false_negative_rate:

### Performance
- avg_scan_time_seconds:
- p95_scan_time_seconds:
- avg_detection_latency_ms:

### Review / workflow impact
- review_time_before_minutes:
- review_time_after_minutes:
- remediation_report_generation_time_seconds:

### Routing / cost
- rules_only_rate:
- classifier_only_rate:
- llm_routing_rate:
- avg_scan_cost_usd:
- llm_cost_reduction_percent:

### Notable experiment findings
- most_common_attack_category:
- hardest_attack_category_to_detect:
- best-performing_detection_strategy:
- biggest_reduction_in_manual_review_time: