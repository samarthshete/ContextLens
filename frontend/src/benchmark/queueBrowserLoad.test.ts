import { describe, expect, it, vi } from 'vitest'
import type { RunListItem } from '../api/types'
import {
  QUEUE_BROWSER_MAX_ROWS,
  QUEUE_BROWSER_STATUS_SLICES,
  loadQueueBrowserRunRows,
} from './queueBrowserLoad'

function item(id: number, created: string): RunListItem {
  return {
    run_id: id,
    status: 'running',
    created_at: created,
    dataset_id: 1,
    query_case_id: 1,
    pipeline_config_id: 1,
    query_text: 'q',
    retrieval_latency_ms: null,
    generation_latency_ms: null,
    evaluation_latency_ms: null,
    total_latency_ms: null,
    evaluator_type: 'none',
    has_evaluation: false,
  }
}

describe('queueBrowserLoad', () => {
  it('merges slices and dedupes by run_id', async () => {
    const listRuns = vi.fn(async (params: { status?: string }) => {
      if (params.status === 'running') {
        return {
          items: [item(1, '2026-01-02T00:00:00Z')],
          total: 1,
          limit: 20,
          offset: 0,
        }
      }
      if (params.status === 'failed') {
        return {
          items: [item(1, '2026-01-02T00:00:00Z'), item(2, '2026-01-01T00:00:00Z')],
          total: 2,
          limit: 20,
          offset: 0,
        }
      }
      return { items: [], total: 0, limit: 20, offset: 0 }
    })
    const { items, sliceErrors } = await loadQueueBrowserRunRows(listRuns)
    expect(sliceErrors).toHaveLength(0)
    expect(items.map((r) => r.run_id).sort((a, b) => a - b)).toEqual([1, 2])
    expect(listRuns).toHaveBeenCalledTimes(QUEUE_BROWSER_STATUS_SLICES.length)
  })

  it('sorts newest first', async () => {
    const listRuns = vi.fn(async (params: { status?: string }) => {
      if (params.status === 'failed') {
        return {
          items: [item(1, '2026-01-01T00:00:00Z'), item(2, '2026-01-03T00:00:00Z')],
          total: 2,
          limit: 20,
          offset: 0,
        }
      }
      return { items: [], total: 0, limit: 20, offset: 0 }
    })
    const { items } = await loadQueueBrowserRunRows(listRuns)
    expect(items.map((r) => r.run_id)).toEqual([2, 1])
  })

  it('records slice errors without throwing', async () => {
    const listRuns = vi.fn(async (params: { status?: string }) => {
      if (params.status === 'pending') throw new Error('network')
      return { items: [item(5, '2026-01-01T00:00:00Z')], total: 1, limit: 20, offset: 0 }
    })
    const { items, sliceErrors } = await loadQueueBrowserRunRows(listRuns)
    expect(items.some((r) => r.run_id === 5)).toBe(true)
    expect(sliceErrors.some((s) => s.includes('pending'))).toBe(true)
  })

  it('caps merged rows at QUEUE_BROWSER_MAX_ROWS', async () => {
    const many = Array.from({ length: QUEUE_BROWSER_MAX_ROWS + 12 }, (_, i) =>
      item(1000 + i, '2026-01-15T00:00:00Z'),
    )
    const listRuns = vi.fn(async (params: { status?: string }) => {
      if (params.status === 'failed') {
        return { items: many, total: many.length, limit: 20, offset: 0 }
      }
      return { items: [], total: 0, limit: 20, offset: 0 }
    })
    const { items } = await loadQueueBrowserRunRows(listRuns)
    expect(items.length).toBe(QUEUE_BROWSER_MAX_ROWS)
  })
})
