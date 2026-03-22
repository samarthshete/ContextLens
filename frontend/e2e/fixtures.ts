import type { Page } from '@playwright/test'

/**
 * Deterministic mock API responses for E2E tests.
 * Shaped to match real GET /api/v1/runs/{id} payloads.
 */

/** `WriteKeyBanner` calls GET /api/v1/meta on load — mock before navigation. */
export async function installApiMetaRoute(
  page: Page,
  options?: { writeProtection?: boolean },
): Promise<void> {
  const writeProtection = options?.writeProtection ?? false
  await page.route('**/api/v1/meta', (route) => {
    if (route.request().method() === 'GET') {
      return route.fulfill({
        json: { write_protection: writeProtection, app_env: 'test' },
        contentType: 'application/json',
      })
    }
    return route.continue()
  })
  await page.route('**/api/v1/meta/verify-write-key', (route) => {
    if (route.request().method() === 'POST') {
      return route.fulfill({ status: 200, json: { ok: true }, contentType: 'application/json' })
    }
    return route.continue()
  })
}

/** A completed heuristic run with retrieval hits but no generation. */
export const HEURISTIC_RUN = {
  run_id: 1,
  status: 'completed',
  created_at: '2026-03-15T10:30:00Z',
  retrieval_latency_ms: 42,
  generation_latency_ms: null,
  evaluation_latency_ms: 8,
  total_latency_ms: 50,
  evaluator_type: 'heuristic',
  query_case: {
    id: 1,
    dataset_id: 1,
    query_text: 'How does ContextLens rank chunks?',
    expected_answer: 'ranks chunks by cosine similarity in pgvector',
  },
  pipeline_config: {
    id: 1,
    name: 'quickstart_top5',
    embedding_model: 'all-MiniLM-L6-v2',
    chunk_strategy: 'fixed',
    chunk_size: 256,
    chunk_overlap: 0,
    top_k: 5,
  },
  retrieval_hits: [
    {
      rank: 1,
      score: 0.812,
      chunk_id: 3,
      document_id: 1,
      content:
        'Dense vector retrieval embeds documents and queries with the same model, then ranks chunks by cosine similarity in pgvector.',
      chunk_index: 0,
    },
    {
      rank: 2,
      score: 0.654,
      chunk_id: 7,
      document_id: 1,
      content:
        'Benchmark runs store one row per query case and pipeline configuration. Measured retrieval latency is written when vector search finishes.',
      chunk_index: 1,
    },
    {
      rank: 3,
      score: 0.521,
      chunk_id: 12,
      document_id: 2,
      content:
        'Evaluation rows may use heuristic scorers that read persisted retrieval scores without calling an external LLM API.',
      chunk_index: 2,
    },
  ],
  generation: null,
  evaluation: {
    faithfulness: null,
    completeness: 0.78,
    retrieval_relevance: 0.66,
    context_coverage: 0.72,
    groundedness: null,
    failure_type: 'NO_FAILURE',
    used_llm_judge: false,
    cost_usd: null,
    metadata_json: {
      evaluator: 'minimal_retrieval_heuristic_v1',
      evaluator_type: 'heuristic',
    },
  },
}

/** A completed full run with generation + LLM judge. */
export const FULL_RUN = {
  run_id: 2,
  status: 'completed',
  created_at: '2026-03-15T11:00:00Z',
  retrieval_latency_ms: 38,
  generation_latency_ms: 3100,
  evaluation_latency_ms: 920,
  total_latency_ms: 4058,
  evaluator_type: 'llm',
  query_case: {
    id: 1,
    dataset_id: 1,
    query_text: 'How does ContextLens rank chunks?',
    expected_answer: 'ranks chunks by cosine similarity in pgvector',
  },
  pipeline_config: {
    id: 1,
    name: 'quickstart_top5',
    embedding_model: 'all-MiniLM-L6-v2',
    chunk_strategy: 'fixed',
    chunk_size: 256,
    chunk_overlap: 0,
    top_k: 5,
  },
  retrieval_hits: [
    {
      rank: 1,
      score: 0.812,
      chunk_id: 3,
      document_id: 1,
      content:
        'Dense vector retrieval embeds documents and queries with the same model, then ranks chunks by cosine similarity in pgvector.',
      chunk_index: 0,
    },
    {
      rank: 2,
      score: 0.654,
      chunk_id: 7,
      document_id: 1,
      content:
        'Benchmark runs store one row per query case and pipeline configuration.',
      chunk_index: 1,
    },
  ],
  generation: {
    answer_text:
      'ContextLens ranks chunks by cosine similarity using pgvector, after embedding both queries and documents with the same model.',
    model_id: 'gpt-4o',
    input_tokens: 480,
    output_tokens: 35,
    metadata_json: { provider: 'openai' },
  },
  evaluation: {
    faithfulness: 0.91,
    completeness: 0.85,
    retrieval_relevance: 0.88,
    context_coverage: 0.80,
    groundedness: 0.87,
    failure_type: 'NO_FAILURE',
    used_llm_judge: true,
    cost_usd: 0.0042,
    metadata_json: {
      evaluator: 'claude_llm_judge_v1',
      evaluator_type: 'llm',
      judge_model: 'claude-sonnet-4-20250514',
      judge_input_tokens: 620,
      judge_output_tokens: 180,
      judge_parse_ok: true,
      judge_retry_attempted: false,
      judge_retry_succeeded: false,
      judge_parse_warnings: [],
    },
  },
}

/** A run with no evaluation and no generation (still running or failed early). */
export const PARTIAL_RUN = {
  run_id: 3,
  status: 'running',
  created_at: '2026-03-15T12:00:00Z',
  retrieval_latency_ms: 55,
  generation_latency_ms: null,
  evaluation_latency_ms: null,
  total_latency_ms: null,
  evaluator_type: 'none',
  query_case: {
    id: 2,
    dataset_id: 1,
    query_text: 'What embedding approach is described?',
    expected_answer: null,
  },
  pipeline_config: {
    id: 2,
    name: 'quickstart_top8',
    embedding_model: 'all-MiniLM-L6-v2',
    chunk_strategy: 'fixed',
    chunk_size: 256,
    chunk_overlap: 0,
    top_k: 8,
  },
  retrieval_hits: [],
  generation: null,
  evaluation: null,
}

/** Empty dashboard summary for mocking. */
export const EMPTY_DASHBOARD_SUMMARY = {
  total_runs: 0,
  status_counts: { completed: 0, failed: 0, in_progress: 0 },
  evaluator_counts: { heuristic: 0, llm: 0, none: 0 },
  latency: {
    avg_retrieval_latency_ms: null,
    avg_generation_latency_ms: null,
    avg_evaluation_latency_ms: null,
    avg_total_latency_ms: null,
  },
  cost: { total_cost_usd: null, avg_cost_usd: null, runs_with_cost: 0, runs_without_cost: 0 },
  failure_type_counts: {},
  recent_runs: [],
}

export const EMPTY_DASHBOARD_ANALYTICS = {
  time_series: [],
  latency_distribution: { retrieval: null, generation: null, evaluation: null, total: null },
  failure_analysis: {
    total_evaluated: 0,
    total_failures: 0,
    failure_rate_pct: 0,
    by_type: {},
    by_config: [],
    recent_failed_runs: [],
  },
  config_insights: [],
}
