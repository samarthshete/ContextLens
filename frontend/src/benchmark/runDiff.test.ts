import { describe, expect, it } from 'vitest'
import type { RunDetail } from '../api/types'
import {
  buildRunDiffModel,
  compareFailureTypes,
  compareLifecycleStatus,
  compareNumbers,
  verdictLabel,
} from './runDiff'

function hit(rank: number, score: number, content: string): RunDetail['retrieval_hits'][number] {
  return {
    rank,
    score,
    chunk_id: rank,
    document_id: 1,
    content,
    chunk_index: rank - 1,
  }
}

function minimalRun(
  id: number,
  over: Partial<Pick<RunDetail, 'retrieval_hits' | 'evaluation' | 'generation' | 'status'>> & {
    query_case_id?: number
    pipeline_config_id?: number
  } = {},
): RunDetail {
  const qcId = over.query_case_id ?? 1
  const pcId = over.pipeline_config_id ?? 1
  return {
    run_id: id,
    status: over.status ?? 'completed',
    created_at: '2026-01-01T00:00:00Z',
    retrieval_latency_ms: 10,
    generation_latency_ms: null,
    evaluation_latency_ms: 5,
    total_latency_ms: 15,
    evaluator_type: 'heuristic',
    query_case: { id: qcId, dataset_id: 1, query_text: 'q', expected_answer: null },
    pipeline_config: {
      id: pcId,
      name: 'p',
      embedding_model: 'm',
      chunk_strategy: 'fixed',
      chunk_size: 256,
      chunk_overlap: 0,
      top_k: 5,
    },
    retrieval_hits: over.retrieval_hits ?? [],
    generation: over.generation ?? null,
    evaluation: over.evaluation ?? null,
  }
}

describe('runDiff', () => {
  describe('compareNumbers', () => {
    it('returns unknown if either side missing', () => {
      expect(compareNumbers(null, 1, true)).toBe('unknown')
      expect(compareNumbers(1, null, true)).toBe('unknown')
    })
    it('higher is better', () => {
      expect(compareNumbers(0.5, 0.8, true)).toBe('improved')
      expect(compareNumbers(0.8, 0.5, true)).toBe('worse')
      expect(compareNumbers(0.5, 0.5, true)).toBe('same')
    })
    it('lower is better', () => {
      expect(compareNumbers(0.02, 0.01, false)).toBe('improved')
      expect(compareNumbers(0.01, 0.02, false)).toBe('worse')
    })
  })

  describe('compareFailureTypes', () => {
    it('treats NO_FAILURE as better', () => {
      expect(compareFailureTypes('RETRIEVAL_MISS', 'NO_FAILURE')).toBe('improved')
      expect(compareFailureTypes('NO_FAILURE', 'RETRIEVAL_MISS')).toBe('worse')
    })
  })

  describe('compareLifecycleStatus', () => {
    it('completed vs failed', () => {
      expect(compareLifecycleStatus('completed', 'failed')).toBe('worse')
      expect(compareLifecycleStatus('failed', 'completed')).toBe('improved')
      expect(compareLifecycleStatus('completed', 'completed')).toBe('same')
    })
  })

  describe('verdictLabel', () => {
    it('maps keys', () => {
      expect(verdictLabel('improved')).toBe('B better')
      expect(verdictLabel('unknown')).toBe('Unknown')
    })
  })

  describe('buildRunDiffModel', () => {
    it('flags more hits and higher top score as improved retrieval', () => {
      const a = minimalRun(101, {
        retrieval_hits: [hit(1, 0.2, 'x')],
        evaluation: { failure_type: 'RETRIEVAL_PARTIAL', used_llm_judge: false },
      })
      const b = minimalRun(102, {
        retrieval_hits: [
          hit(1, 0.85, 'a'),
          hit(2, 0.8, 'b'),
          hit(3, 0.7, 'c'),
          hit(4, 0.6, 'd'),
          hit(5, 0.5, 'e'),
        ],
        evaluation: { failure_type: 'NO_FAILURE', used_llm_judge: false },
      })
      const m = buildRunDiffModel(a, b)
      expect(m.rows.find((r) => r.id === 'retrieval_hits')?.verdict).toBe('improved')
      expect(m.rows.find((r) => r.id === 'top_score')?.verdict).toBe('improved')
      expect(m.rows.find((r) => r.id === 'failure_type')?.verdict).toBe('improved')
      expect(m.summaryLines.some((l) => /stronger retrieval/i.test(l))).toBe(true)
    })

    it('adds warnings when query or config differ', () => {
      const a = minimalRun(1, { query_case_id: 1, pipeline_config_id: 1 })
      const b = minimalRun(2, { query_case_id: 2, pipeline_config_id: 2 })
      const m = buildRunDiffModel(a, b)
      expect(m.warnings.length).toBe(2)
    })
  })
})
