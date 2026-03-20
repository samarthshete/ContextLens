import { API_BASE } from '../config'
import type {
  ConfigComparisonResponse,
  Dataset,
  DocumentListItem,
  DocumentResponse,
  PipelineConfig,
  QueryCase,
  RunCreateBody,
  RunCreateOutcome,
  RunCreateResponse,
  RunDetail,
  RunListResponse,
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

export const api = {
  listDatasets: () => apiFetch<Dataset[]>('/datasets'),

  listQueryCases: (datasetId?: number) => {
    const q = datasetId != null ? `?dataset_id=${datasetId}` : ''
    return apiFetch<QueryCase[]>(`/query-cases${q}`)
  },

  listPipelineConfigs: () => apiFetch<PipelineConfig[]>('/pipeline-configs'),

  listDocuments: () => apiFetch<DocumentListItem[]>('/documents'),

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

  listRuns: (params?: { limit?: number; offset?: number }) => {
    const sp = new URLSearchParams()
    if (params?.limit != null) sp.set('limit', String(params.limit))
    if (params?.offset != null) sp.set('offset', String(params.offset))
    const q = sp.toString()
    return apiFetch<RunListResponse>(`/runs${q ? `?${q}` : ''}`)
  },

  getRun: (runId: number) => apiFetch<RunDetail>(`/runs/${runId}`),

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
