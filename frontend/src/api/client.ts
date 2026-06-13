import { API_BASE } from '../config'
import { getStoredWriteKey } from '../lib/writeKeyStorage'
import type {
  ConfigComparisonResponse,
  DashboardAnalyticsResponse,
  Dataset,
  DatasetCreateBody,
  DatasetUpdateBody,
  DocumentChunk,
  DocumentListItem,
  DocumentResponse,
  PipelineConfig,
  PipelineConfigCreateBody,
  PipelineConfigUpdateBody,
  QueryCase,
  QueryCaseCreateBody,
  QueryCaseUpdateBody,
  RunCreateBody,
  DiagnosisTimingSession,
  DashboardSummaryResponse,
  RunCreateOutcome,
  RunCreateResponse,
  RunDetail,
  ListRunsParams,
  RunListResponse,
  RunQueueStatusResponse,
  RunRequeueResponse,
} from './types'

export type DocumentUploadOptions = {
  chunk_strategy?: 'fixed' | 'recursive'
  chunk_size?: number
  chunk_overlap?: number
}

export class ApiError extends Error {
  status: number
  detail: string
  code: string | null
  retryable: boolean | null
  requestId: string | null

  constructor(
    status: number,
    detail: string,
    options?: { code?: string | null; retryable?: boolean | null; requestId?: string | null },
  ) {
    super(detail)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
    this.code = options?.code ?? null
    this.retryable = options?.retryable ?? null
    this.requestId = options?.requestId ?? null
  }
}

/** Attach write-key header when set (optional hosted protection). */
export function writeKeyHeaders(
  base: Record<string, string>,
  keyOverride?: string,
): Record<string, string> {
  const k = (keyOverride ?? getStoredWriteKey())?.trim()
  if (!k) return base
  return { ...base, 'X-ContextLens-Write-Key': k }
}

export type ApiMetaResponse = {
  write_protection: boolean
  app_env: string
}

type ApiErrorBody = {
  detail?: unknown
  error?: {
    code?: unknown
    message?: unknown
    retryable?: unknown
    request_id?: unknown
  }
}

async function parseError(res: Response): Promise<ApiError> {
  let body: ApiErrorBody | null = null
  try {
    body = (await res.json()) as ApiErrorBody
  } catch {
    body = null
  }
  const envelope = body?.error
  const message =
    typeof envelope?.message === 'string'
      ? envelope.message
      : typeof body?.detail === 'string'
        ? body.detail
        : Array.isArray(body?.detail)
          ? JSON.stringify(body.detail)
          : res.statusText || `HTTP ${res.status}`
  return new ApiError(res.status, message, {
    code: typeof envelope?.code === 'string' ? envelope.code : null,
    retryable: typeof envelope?.retryable === 'boolean' ? envelope.retryable : null,
    requestId: typeof envelope?.request_id === 'string' ? envelope.request_id : null,
  })
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${API_BASE}${path.startsWith('/') ? path : `/${path}`}`
  const baseHeaders: Record<string, string> = {
    Accept: 'application/json',
    ...(init?.headers as Record<string, string>),
  }
  const res = await fetch(url, {
    ...init,
    headers: writeKeyHeaders(baseHeaders),
  })
  if (!res.ok) {
    throw await parseError(res)
  }
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

/** Public capability metadata (same origin as other API calls). */
export async function fetchApiMeta(): Promise<ApiMetaResponse> {
  return apiFetch<ApiMetaResponse>('/meta')
}

/** Check a candidate key before storing in sessionStorage. */
export async function verifyWriteKey(candidate: string): Promise<boolean> {
  const res = await fetch(`${API_BASE}/meta/verify-write-key`, {
    method: 'POST',
    headers: writeKeyHeaders({ Accept: 'application/json' }, candidate),
  })
  return res.ok
}

async function apiJson<T>(path: string, method: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json' }
  const init: RequestInit = { method, headers }
  if (body !== undefined) {
    headers['Content-Type'] = 'application/json'
    init.body = JSON.stringify(body)
  }
  return apiFetch<T>(path, init)
}

export const api = {
  listDatasets: () => apiFetch<Dataset[]>('/datasets'),

  createDataset: (body: DatasetCreateBody) => apiJson<Dataset>('/datasets', 'POST', body),

  updateDataset: (id: number, body: DatasetUpdateBody) =>
    apiJson<Dataset>(`/datasets/${id}`, 'PATCH', body),

  deleteDataset: (id: number) => apiJson<void>(`/datasets/${id}`, 'DELETE'),

  listQueryCases: (datasetId?: number) => {
    const q = datasetId != null ? `?dataset_id=${datasetId}` : ''
    return apiFetch<QueryCase[]>(`/query-cases${q}`)
  },

  createQueryCase: (body: QueryCaseCreateBody) => apiJson<QueryCase>('/query-cases', 'POST', body),

  updateQueryCase: (id: number, body: QueryCaseUpdateBody) =>
    apiJson<QueryCase>(`/query-cases/${id}`, 'PATCH', body),

  deleteQueryCase: (id: number) => apiJson<void>(`/query-cases/${id}`, 'DELETE'),

  listPipelineConfigs: () => apiFetch<PipelineConfig[]>('/pipeline-configs'),

  createPipelineConfig: (body: PipelineConfigCreateBody) =>
    apiJson<PipelineConfig>('/pipeline-configs', 'POST', body),

  updatePipelineConfig: (id: number, body: PipelineConfigUpdateBody) =>
    apiJson<PipelineConfig>(`/pipeline-configs/${id}`, 'PATCH', body),

  deletePipelineConfig: (id: number) => apiJson<void>(`/pipeline-configs/${id}`, 'DELETE'),

  listDocuments: () => apiFetch<DocumentListItem[]>('/documents'),

  getDocument: (id: number) => apiFetch<DocumentResponse>(`/documents/${id}`),

  getDocumentChunks: (id: number) => apiFetch<DocumentChunk[]>(`/documents/${id}/chunks`),

  /**
   * Multipart upload to ``POST /documents`` (ingest + chunk + embed).
   * Do not set ``Content-Type`` — the browser sets the multipart boundary.
   */
  uploadDocument: async (
    file: File,
    options?: DocumentUploadOptions,
  ): Promise<DocumentResponse> => {
    const sp = new URLSearchParams()
    sp.set('chunk_strategy', options?.chunk_strategy ?? 'fixed')
    sp.set('chunk_size', String(options?.chunk_size ?? 512))
    sp.set('chunk_overlap', String(options?.chunk_overlap ?? 0))
    const url = `${API_BASE}/documents?${sp.toString()}`
    const body = new FormData()
    body.append('file', file)
    const res = await fetch(url, {
      method: 'POST',
      headers: writeKeyHeaders({ Accept: 'application/json' }),
      body,
    })
    if (!res.ok) {
      throw await parseError(res)
    }
    return res.json() as Promise<DocumentResponse>
  },

  createRun: async (body: RunCreateBody): Promise<RunCreateOutcome> => {
    const url = `${API_BASE}/runs`
    const res = await fetch(url, {
      method: 'POST',
      headers: writeKeyHeaders({
        Accept: 'application/json',
        'Content-Type': 'application/json',
      }),
      body: JSON.stringify({
        ...body,
        document_id: body.document_id ?? undefined,
      }),
    })
    if (!res.ok) {
      throw await parseError(res)
    }
    const data = (await res.json()) as RunCreateResponse
    return { ...data, httpStatus: res.status }
  },

  dashboardSummary: (params?: { datasetId: number }) => {
    const q =
      params != null && params.datasetId != null
        ? `?dataset_id=${encodeURIComponent(String(params.datasetId))}`
        : ''
    return apiFetch<DashboardSummaryResponse>(`/runs/dashboard-summary${q}`)
  },

  dashboardAnalytics: (params?: { datasetId: number }) => {
    const q =
      params != null && params.datasetId != null
        ? `?dataset_id=${encodeURIComponent(String(params.datasetId))}`
        : ''
    return apiFetch<DashboardAnalyticsResponse>(`/runs/dashboard-analytics${q}`)
  },

  listRuns: (params?: ListRunsParams) => {
    const sp = new URLSearchParams()
    if (params?.limit != null) sp.set('limit', String(params.limit))
    if (params?.offset != null) sp.set('offset', String(params.offset))
    if (params?.dataset_id != null) sp.set('dataset_id', String(params.dataset_id))
    if (params?.pipeline_config_id != null) {
      sp.set('pipeline_config_id', String(params.pipeline_config_id))
    }
    if (params?.evaluator_type != null) sp.set('evaluator_type', params.evaluator_type)
    if (params?.status != null && params.status !== '') sp.set('status', params.status)
    const q = sp.toString()
    return apiFetch<RunListResponse>(`/runs${q ? `?${q}` : ''}`)
  },

  getRun: (runId: number) => apiFetch<RunDetail>(`/runs/${runId}`),

  listDiagnosisTimingSessions: (runId: number) =>
    apiFetch<DiagnosisTimingSession[]>(`/runs/${runId}/diagnosis-timing-sessions`),

  createDiagnosisTimingSession: (
    runId: number,
    body: {
      mode: 'manual' | 'assisted'
      started_at?: string | null
      session_key?: string | null
      synthetic?: boolean
    },
  ) => apiJson<DiagnosisTimingSession>(`/runs/${runId}/diagnosis-timing-sessions`, 'POST', body),

  patchDiagnosisTimingSession: (
    runId: number,
    sessionId: number,
    body: {
      first_meaningful_insight_at?: string | null
      completed_at?: string | null
      resolution_label?: string | null
      notes?: string | null
    },
  ) =>
    apiJson<DiagnosisTimingSession>(
      `/runs/${runId}/diagnosis-timing-sessions/${sessionId}`,
      'PATCH',
      body,
    ),

  getRunQueueStatus: (runId: number) =>
    apiFetch<RunQueueStatusResponse>(`/runs/${runId}/queue-status`),

  requeueRun: (runId: number) =>
    apiJson<RunRequeueResponse>(`/runs/${runId}/requeue`, 'POST'),

  configComparison: (
    pipelineConfigIds: number[],
    options?: {
      evaluatorType?: 'heuristic' | 'llm' | 'both'
      /** When set, matches dashboard ``dataset_id`` scope (includes benchmark_realism runs for that dataset). */
      datasetId?: number | null
    },
  ) => {
    const sp = new URLSearchParams()
    for (const id of pipelineConfigIds) {
      sp.append('pipeline_config_ids', String(id))
    }
    sp.set('evaluator_type', options?.evaluatorType ?? 'both')
    if (options?.datasetId != null) {
      sp.set('dataset_id', String(options.datasetId))
    }
    return apiFetch<ConfigComparisonResponse>(`/runs/config-comparison?${sp.toString()}`)
  },
}
