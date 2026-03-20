/** Mirrors backend list/detail JSON (subset used by UI). */

export interface Dataset {
  id: number
  name: string
  description: string | null
  created_at: string
}

export interface QueryCase {
  id: number
  dataset_id: number
  query_text: string
  expected_answer: string | null
  metadata_json: Record<string, unknown> | null
}

export interface PipelineConfig {
  id: number
  name: string
  embedding_model: string
  chunk_strategy: string
  chunk_size: number
  chunk_overlap: number
  top_k: number
  created_at: string
}

export interface DocumentListItem {
  id: number
  title: string
  source_type: string
  status: string
  created_at: string
}

/** ``POST /documents`` response (same shape as document detail). */
export interface DocumentResponse extends DocumentListItem {
  metadata_json: Record<string, unknown> | null
}

export interface RunCreateBody {
  query_case_id: number
  pipeline_config_id: number
  eval_mode: 'heuristic' | 'full'
  document_id?: number | null
}

export interface RunCreateResponse {
  run_id: number
  status: string
  eval_mode: string
  /** RQ job id when ``eval_mode`` is ``full``. */
  job_id?: string | null
}

/** ``POST /runs`` returns **201** (heuristic done) or **202** (full run accepted). */
export type RunCreateOutcome = RunCreateResponse & { httpStatus: number }

export interface RunListItem {
  run_id: number
  status: string
  created_at: string
  dataset_id: number
  query_case_id: number
  pipeline_config_id: number
  query_text: string
  retrieval_latency_ms: number | null
  generation_latency_ms: number | null
  evaluation_latency_ms: number | null
  total_latency_ms: number | null
  evaluator_type: string
  has_evaluation: boolean
}

export interface RunListResponse {
  items: RunListItem[]
  total: number
  limit: number
  offset: number
}

export interface ConfigComparisonMetrics {
  pipeline_config_id: number
  traced_runs: number
  avg_retrieval_latency_ms: number | null
  p95_retrieval_latency_ms: number | null
  avg_evaluation_latency_ms: number | null
  p95_evaluation_latency_ms: number | null
  avg_total_latency_ms: number | null
  p95_total_latency_ms: number | null
  avg_groundedness: number | null
  avg_completeness: number | null
  avg_retrieval_relevance: number | null
  avg_context_coverage: number | null
  failure_type_counts: Record<string, number>
  avg_evaluation_cost_per_run_usd: number | null
}

export interface ConfigComparisonResponse {
  evaluator_type: string
  pipeline_config_ids: number[]
  configs: ConfigComparisonMetrics[] | null
  buckets: Record<string, ConfigComparisonMetrics[]> | null
}

/** Run detail — aligned with `RunDetailResponse` (JSON). */
export interface RunDetail {
  run_id: number
  status: string
  created_at: string
  retrieval_latency_ms: number | null
  generation_latency_ms: number | null
  evaluation_latency_ms: number | null
  total_latency_ms: number | null
  evaluator_type: string
  query_case: {
    id: number
    dataset_id: number
    query_text: string
    expected_answer: string | null
  }
  pipeline_config: {
    id: number
    name: string
    embedding_model: string
    chunk_strategy: string
    chunk_size: number
    chunk_overlap: number
    top_k: number
  }
  retrieval_hits: Array<{
    rank: number
    score: number
    chunk_id: number
    document_id: number
    content: string
    chunk_index: number
  }>
  generation: Record<string, unknown> | null
  evaluation: Record<string, unknown> | null
}
