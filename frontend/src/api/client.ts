import { API_BASE } from '../config'
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

  constructor(status: number, detail: string) {
    super(detail)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

async function parseError(res: Response): Promise<string> {
  try {
    const j = (await res.json()) as { detail?: unknown }
    if (typeof j.detail === 'string') return j.detail
    if (Array.isArray(j.detail)) return JSON.stringify(j.detail)
    return res.statusText || `HTTP ${res.status}`
  } catch {
    return res.statusText || `HTTP ${res.status}`
  }
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${API_BASE}${path.startsWith('/') ? path : `/${path}`}`
  const res = await fetch(url, {
    ...init,
    headers: {
      Accept: 'application/json',
      ...(init?.headers as Record<string, string>),
    },
  })
  if (!res.ok) {
    throw new ApiError(res.status, await parseError(res))
  }
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
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
      headers: { Accept: 'application/json' },
      body,
    })
    if (!res.ok) {
      throw new ApiError(res.status, await parseError(res))
    }
    return res.json() as Promise<DocumentResponse>
  },

  createRun: async (body: RunCreateBody): Promise<RunCreateOutcome> => {
    const url = `${API_BASE}/runs`
    const res = await fetch(url, {
      method: 'POST',
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        ...body,
        document_id: body.document_id ?? undefined,
      }),
    })
    const data = (await res.json()) as RunCreateResponse
    if (!res.ok) {
      throw new ApiError(res.status, await parseError(res))
    }
    return { ...data, httpStatus: res.status }
  },

  dashboardSummary: () => apiFetch<DashboardSummaryResponse>('/runs/dashboard-summary'),

  dashboardAnalytics: () => apiFetch<DashboardAnalyticsResponse>('/runs/dashboard-analytics'),

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

  getRunQueueStatus: (runId: number) =>
    apiFetch<RunQueueStatusResponse>(`/runs/${runId}/queue-status`),

  requeueRun: (runId: number) =>
    apiJson<RunRequeueResponse>(`/runs/${runId}/requeue`, 'POST'),

  configComparison: (
    pipelineConfigIds: number[],
    options?: {
      evaluatorType?: 'heuristic' | 'llm' | 'both'
      combineEvaluators?: boolean
    },
  ) => {
    const sp = new URLSearchParams()
    for (const id of pipelineConfigIds) {
      sp.append('pipeline_config_ids', String(id))
    }
    sp.set('evaluator_type', options?.evaluatorType ?? 'both')
    if (options?.combineEvaluators) {
      sp.set('combine_evaluators', 'true')
    }
    return apiFetch<ConfigComparisonResponse>(`/runs/config-comparison?${sp.toString()}`)
  },
}
