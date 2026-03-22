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

/** ``GET /documents/{id}/chunks`` row. */
export interface DocumentChunk {
  id: number
  document_id: number
  content: string
  chunk_index: number
  start_char: number | null
  end_char: number | null
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

/** Query params for `GET /runs` (backend-supported filters + pagination). */
export interface ListRunsParams {
  limit?: number
  offset?: number
  dataset_id?: number
  pipeline_config_id?: number
  evaluator_type?: 'heuristic' | 'llm'
  status?: string
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

/** ``GET /runs/dashboard-summary`` — observability aggregates. */
export interface DashboardStatusCounts {
  completed: number
  failed: number
  in_progress: number
}

export interface DashboardEvaluatorCounts {
  heuristic_runs: number
  llm_runs: number
  runs_without_evaluation: number
}

export interface DashboardLatencySummary {
  avg_retrieval_latency_ms: number | null
  avg_generation_latency_ms: number | null
  avg_evaluation_latency_ms: number | null
  avg_total_latency_ms: number | null
}

export interface DashboardCostSummary {
  total_cost_usd: number | null
  avg_cost_usd: number | null
  evaluation_rows_with_cost: number
  evaluation_rows_cost_not_available: number
}

export interface DashboardRecentRun {
  run_id: number
  status: string
  created_at: string
  evaluator_type: string
  total_latency_ms: number | null
  cost_usd: number | null
  failure_type: string | null
}

export interface DashboardSummaryResponse {
  total_runs: number
  status_counts: DashboardStatusCounts
  evaluator_counts: DashboardEvaluatorCounts
  latency: DashboardLatencySummary
  cost: DashboardCostSummary
  failure_type_counts: Record<string, number>
  recent_runs: DashboardRecentRun[]
}

/** Run detail — aligned with `RunDetailResponse` (JSON). */
/** POST/PATCH bodies for registry (subset of backend schemas). */
export interface DatasetCreateBody {
  name: string
  description?: string | null
}

export interface DatasetUpdateBody {
  name?: string
  description?: string | null
}

export interface QueryCaseCreateBody {
  dataset_id: number
  query_text: string
  expected_answer?: string | null
}

export interface QueryCaseUpdateBody {
  dataset_id?: number
  query_text?: string
  expected_answer?: string | null
}

export interface PipelineConfigCreateBody {
  name: string
  embedding_model: string
  chunk_strategy: string
  chunk_size: number
  chunk_overlap: number
  top_k: number
}

export interface PipelineConfigUpdateBody {
  name?: string
  embedding_model?: string
  chunk_strategy?: string
  chunk_size?: number
  chunk_overlap?: number
  top_k?: number
}

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

/** `GET /runs/{id}/queue-status` — aligned with `RunQueueStatusResponse`. */
export interface RunQueueStatusResponse {
  run_id: number
  run_status: string
  pipeline: 'heuristic' | 'full'
  job_id: string | null
  rq_job_status: string | null
  lock_present: boolean
  requeue_eligible: boolean
  detail: string | null
}

/** GET /api/v1/runs/dashboard-analytics — richer analytics. */
export interface TimeSeriesDay {
  date: string
  runs: number
  completed: number
  failed: number
  avg_total_latency_ms: number | null
  avg_cost_usd: number | null
  failure_count: number
}

export interface LatencyDistribution {
  count: number
  min_ms: number | null
  max_ms: number | null
  avg_ms: number | null
  median_ms: number | null
  p95_ms: number | null
}

export interface LatencyDistributionSection {
  retrieval: LatencyDistribution
  generation: LatencyDistribution
  evaluation: LatencyDistribution
  total: LatencyDistribution
}

export interface FailureByConfig {
  pipeline_config_id: number
  pipeline_config_name: string
  failure_counts: Record<string, number>
  total_failures: number
}

export interface RecentFailedRun {
  run_id: number
  status: string
  created_at: string
  failure_type: string | null
  pipeline_config_id: number
}

export interface FailureAnalysisSection {
  overall_counts: Record<string, number>
  overall_percentages: Record<string, number>
  by_config: FailureByConfig[]
  recent_failed_runs: RecentFailedRun[]
}

export interface ConfigInsight {
  pipeline_config_id: number
  pipeline_config_name: string
  traced_runs: number
  completed_runs: number
  failed_runs: number
  avg_total_latency_ms: number | null
  min_total_latency_ms: number | null
  max_total_latency_ms: number | null
  avg_cost_usd: number | null
  total_cost_usd: number | null
  avg_retrieval_relevance: number | null
  avg_context_coverage: number | null
  avg_completeness: number | null
  avg_faithfulness: number | null
  latest_run_at: string | null
  top_failure_type: string | null
}

export interface DashboardAnalyticsResponse {
  time_series: TimeSeriesDay[]
  latency_distribution: LatencyDistributionSection
  failure_analysis: FailureAnalysisSection
  config_insights: ConfigInsight[]
}

/** `POST /runs/{id}/requeue` — **202** body. */
export interface RunRequeueResponse {
  run_id: number
  status: string
  job_id: string
}
