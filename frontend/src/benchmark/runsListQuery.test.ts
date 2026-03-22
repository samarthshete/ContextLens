import { describe, expect, it } from 'vitest'
import type { RunListItem } from '../api/types'
import {
  RUNS_LIST_FILTERS_INIT,
  buildListRunsApiParams,
  narrowRunsOnPage,
} from './runsListQuery'

function item(partial: Partial<RunListItem> & Pick<RunListItem, 'run_id' | 'query_text'>): RunListItem {
  return {
    status: 'completed',
    created_at: '2026-01-01T00:00:00Z',
    dataset_id: 1,
    query_case_id: 1,
    pipeline_config_id: 1,
    retrieval_latency_ms: null,
    generation_latency_ms: null,
    evaluation_latency_ms: null,
    total_latency_ms: null,
    evaluator_type: 'heuristic',
    has_evaluation: true,
    ...partial,
  }
}

describe('runsListQuery', () => {
  describe('buildListRunsApiParams', () => {
    it('returns empty object for initial filters', () => {
      expect(buildListRunsApiParams(RUNS_LIST_FILTERS_INIT)).toEqual({})
    })

    it('maps status, evaluator, dataset, pipeline', () => {
      expect(
        buildListRunsApiParams({
          ...RUNS_LIST_FILTERS_INIT,
          status: 'failed',
          evaluatorType: 'llm',
          datasetId: 3,
          pipelineConfigId: 7,
        }),
      ).toEqual({
        status: 'failed',
        evaluator_type: 'llm',
        dataset_id: 3,
        pipeline_config_id: 7,
      })
    })

    it('ignores blank status', () => {
      expect(
        buildListRunsApiParams({
          ...RUNS_LIST_FILTERS_INIT,
          status: '   ',
        }),
      ).toEqual({})
    })
  })

  describe('narrowRunsOnPage', () => {
    const configs = [{ id: 1, name: 'MyPipe' }]

    it('returns all when narrow text empty', () => {
      const rows = [item({ run_id: 1, query_text: 'a' }), item({ run_id: 2, query_text: 'b' })]
      expect(narrowRunsOnPage(rows, '', configs)).toHaveLength(2)
    })

    it('filters by run id substring', () => {
      const rows = [item({ run_id: 100, query_text: 'x' }), item({ run_id: 20, query_text: 'y' })]
      expect(narrowRunsOnPage(rows, '10', configs).map((r) => r.run_id)).toEqual([100])
    })

    it('filters by query text case-insensitively', () => {
      const rows = [
        item({ run_id: 1, query_text: 'Hello World' }),
        item({ run_id: 2, query_text: 'Other' }),
      ]
      expect(narrowRunsOnPage(rows, 'world', configs)).toHaveLength(1)
      expect(narrowRunsOnPage(rows, 'world', configs)[0].run_id).toBe(1)
    })

    it('matches pipeline display label', () => {
      const rows = [item({ run_id: 1, query_text: 'q', pipeline_config_id: 1 })]
      expect(narrowRunsOnPage(rows, 'mypipe', configs)).toHaveLength(1)
    })
  })
})
