/**
 * Pure helpers for Recent runs list: server filter params (GET /runs) and client-side narrowing.
 */

import type { PipelineConfig, RunListItem } from '../api/types'

export type RunsListServerFilters = {
  status: string
  evaluatorType: '' | 'heuristic' | 'llm'
  datasetId: number | ''
  pipelineConfigId: number | ''
}

export const RUNS_LIST_FILTERS_INIT: RunsListServerFilters = {
  status: '',
  evaluatorType: '',
  datasetId: '',
  pipelineConfigId: '',
}

/** Status values aligned with backend Run lifecycle (subset for filter dropdown). */
export const RUN_FILTER_STATUS_VALUES = [
  'completed',
  'failed',
  'pending',
  'running',
  'retrieval_completed',
  'generation_completed',
] as const

export type ListRunsQueryParams = {
  status?: string
  evaluator_type?: 'heuristic' | 'llm'
  dataset_id?: number
  pipeline_config_id?: number
}

export function buildListRunsApiParams(f: RunsListServerFilters): ListRunsQueryParams {
  const p: ListRunsQueryParams = {}
  const st = f.status.trim()
  if (st) p.status = st
  if (f.evaluatorType === 'heuristic' || f.evaluatorType === 'llm') {
    p.evaluator_type = f.evaluatorType
  }
  if (f.datasetId !== '') p.dataset_id = Number(f.datasetId)
  if (f.pipelineConfigId !== '') p.pipeline_config_id = Number(f.pipelineConfigId)
  return p
}

function pipelineLabelLower(id: number, pipelineConfigs: Pick<PipelineConfig, 'id' | 'name'>[]): string {
  const c = pipelineConfigs.find((x) => x.id === id)
  return (c ? `${c.name} (#${id})` : `config #${id}`).toLowerCase()
}

/**
 * Client-only filter over rows already returned for the current page (does not change server query).
 * Matches run id, status, evaluator label, query text, dataset/pipeline ids, pipeline display label.
 */
export function narrowRunsOnPage(
  items: RunListItem[],
  narrowText: string,
  pipelineConfigs: Pick<PipelineConfig, 'id' | 'name'>[],
): RunListItem[] {
  const raw = narrowText.trim().toLowerCase()
  if (!raw) return items
  return items.filter((r) => {
    if (String(r.run_id).includes(raw)) return true
    if (r.status.toLowerCase().includes(raw)) return true
    if (r.evaluator_type.toLowerCase().includes(raw)) return true
    if (r.query_text.toLowerCase().includes(raw)) return true
    if (String(r.pipeline_config_id).includes(raw)) return true
    if (String(r.dataset_id).includes(raw)) return true
    if (pipelineLabelLower(r.pipeline_config_id, pipelineConfigs).includes(raw)) return true
    return false
  })
}
