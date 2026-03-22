import { describe, expect, it } from 'vitest'
import type { RunDetail } from '../api/types'
import {
  computeContextQuality,
  computeRetrievalDiagnosis,
  computeRunDiagnosisSummary,
  evaluationScoreRows,
  extractGenerationJudgeInsights,
} from './runDiagnosis'

function baseRun(over: Partial<RunDetail> = {}): RunDetail {
  return {
    run_id: 1,
    status: 'completed',
    created_at: '2026-01-01T00:00:00Z',
    retrieval_latency_ms: 10,
    generation_latency_ms: null,
    evaluation_latency_ms: 5,
    total_latency_ms: 15,
    evaluator_type: 'heuristic',
    query_case: { id: 1, dataset_id: 1, query_text: 'q', expected_answer: null },
    pipeline_config: {
      id: 1,
      name: 'p',
      embedding_model: 'm',
      chunk_strategy: 'fixed',
      chunk_size: 256,
      chunk_overlap: 0,
      top_k: 5,
    },
    retrieval_hits: [],
    generation: null,
    evaluation: null,
    ...over,
  }
}

/** Long chunk text so thin-context heuristic stays off in “clean run” scenarios. */
const LONG = 'word '.repeat(55)

function diagnosisSummaryFor(run: RunDetail) {
  const r = computeRetrievalDiagnosis(run.retrieval_hits)
  const c = computeContextQuality(run.retrieval_hits, run.pipeline_config.top_k)
  const gj = extractGenerationJudgeInsights(run.generation, run.evaluation)
  return computeRunDiagnosisSummary(run, r, c, gj)
}

describe('runDiagnosis', () => {
  describe('computeRetrievalDiagnosis', () => {
    it('handles zero hits', () => {
      const d = computeRetrievalDiagnosis([])
      expect(d.hitCount).toBe(0)
      expect(d.topScore).toBeNull()
      expect(d.rank1MinusRank2).toBeNull()
      expect(d.interpretations.some((s) => /No chunks/i.test(s))).toBe(true)
    })

    it('computes gap and sorts by rank', () => {
      const d = computeRetrievalDiagnosis([
        { rank: 2, score: 0.5, chunk_id: 2, document_id: 1, content: 'b', chunk_index: 1 },
        { rank: 1, score: 0.8, chunk_id: 1, document_id: 1, content: 'a', chunk_index: 0 },
      ])
      expect(d.hitCount).toBe(2)
      expect(d.topScore).toBe(0.8)
      expect(d.rank1MinusRank2).toBeCloseTo(0.3, 5)
    })

    it('warns when three or more hits all share one document', () => {
      const mk = (rank: number, chunk_id: number) => ({
        rank,
        chunk_id,
        score: 0.7,
        document_id: 42,
        content: 'x',
        chunk_index: 0,
      })
      const d = computeRetrievalDiagnosis([mk(1, 1), mk(2, 2), mk(3, 3)])
      expect(d.interpretations.some((s) => /same document/i.test(s))).toBe(true)
    })
  })

  describe('computeContextQuality', () => {
    it('flags duplicate chunks', () => {
      const body = 'same text'
      const q = computeContextQuality(
        [
          { rank: 1, score: 1, chunk_id: 1, document_id: 1, content: body, chunk_index: 0 },
          { rank: 2, score: 0.9, chunk_id: 2, document_id: 1, content: body, chunk_index: 1 },
        ],
        5,
      )
      expect(q.repetitiveWarning).toBeTruthy()
    })

    it('flags sparse context for top_k=3 with only one hit', () => {
      const q = computeContextQuality(
        [{ rank: 1, score: 0.9, chunk_id: 1, document_id: 1, content: LONG, chunk_index: 0 }],
        3,
      )
      expect(q.sparseContext).toBe(true)
      expect(q.notes.some((n) => /top_k/i.test(n))).toBe(true)
    })

    it('does not flag sparse for top_k=3 when two of three hits returned', () => {
      const q = computeContextQuality(
        [
          { rank: 1, score: 0.9, chunk_id: 1, document_id: 1, content: LONG, chunk_index: 0 },
          { rank: 2, score: 0.8, chunk_id: 2, document_id: 2, content: LONG, chunk_index: 0 },
        ],
        3,
      )
      expect(q.sparseContext).toBe(false)
    })

    it('flags sparse for top_k=5 with only two hits', () => {
      const q = computeContextQuality(
        [
          { rank: 1, score: 0.9, chunk_id: 1, document_id: 1, content: LONG, chunk_index: 0 },
          { rank: 2, score: 0.8, chunk_id: 2, document_id: 2, content: LONG, chunk_index: 0 },
        ],
        5,
      )
      expect(q.sparseContext).toBe(true)
    })

    it('flags long suffix-to-prefix overlap between consecutive chunks', () => {
      const bridge = 'y'.repeat(85)
      const q = computeContextQuality(
        [
          { rank: 1, score: 1, chunk_id: 1, document_id: 1, content: `aaa ${bridge}`, chunk_index: 0 },
          { rank: 2, score: 0.9, chunk_id: 2, document_id: 1, content: `${bridge} bbb`, chunk_index: 1 },
        ],
        5,
      )
      expect(q.repetitiveWarning).toMatch(/tail\/head overlap/i)
    })
  })

  describe('extractGenerationJudgeInsights', () => {
    it('reads models and tokens from payload', () => {
      const g = extractGenerationJudgeInsights(
        {
          answer_text: 'hi',
          model_id: 'gpt-4o',
          input_tokens: 10,
          output_tokens: 20,
          metadata_json: { provider: 'openai' },
        },
        {
          faithfulness: 0.9,
          used_llm_judge: true,
          cost_usd: 0.001,
          metadata_json: {
            judge_model: 'judge-1',
            judge_input_tokens: 100,
            judge_output_tokens: 50,
            judge_parse_ok: true,
          },
        },
      )
      expect(g.generationModel).toBe('gpt-4o')
      expect(g.judgeModel).toBe('judge-1')
      expect(g.genInputTokens).toBe(10)
      expect(g.judgeOutputTokens).toBe(50)
      expect(g.totalCostUsd).toBe(0.001)
    })

    it('adds retry badge when retry attempted', () => {
      const g = extractGenerationJudgeInsights(null, {
        used_llm_judge: true,
        metadata_json: {
          judge_retry_attempted: true,
          judge_retry_succeeded: true,
          judge_parse_ok: true,
        },
      })
      expect(g.badges.some((b) => b.key === 'retry-ok')).toBe(true)
    })
  })

  describe('evaluationScoreRows', () => {
    it('returns empty when evaluation is null', () => {
      expect(evaluationScoreRows(null)).toEqual([])
    })

    it('formats scores and failure type', () => {
      const rows = evaluationScoreRows({
        faithfulness: 0.812,
        completeness: null,
        retrieval_relevance: 0.5,
        context_coverage: 0.6,
        groundedness: 0.7,
        failure_type: 'NO_FAILURE',
        used_llm_judge: true,
      })
      expect(rows.find((r) => r.label === 'Faithfulness')?.value).toBe('0.812')
      expect(rows.find((r) => r.label === 'Completeness')?.value).toBe('N/A')
      expect(rows.find((r) => r.label === 'Failure type')?.value).toBe('NO_FAILURE')
      expect(rows.find((r) => r.label === 'LLM judge used')?.value).toBe('yes')
    })
  })

  describe('computeRunDiagnosisSummary', () => {
    it('flags retrieval miss', () => {
      const run = baseRun({
        retrieval_hits: [],
        evaluation: { failure_type: 'RETRIEVAL_MISS', used_llm_judge: false },
      })
      const lines = diagnosisSummaryFor(run)
      expect(lines.some((l) => l.key === 'retrieval')).toBe(true)
    })

    it('adds explicit line for RETRIEVAL_PARTIAL', () => {
      const lines = diagnosisSummaryFor(
        baseRun({
          retrieval_hits: [
            { rank: 1, score: 0.5, chunk_id: 1, document_id: 1, content: LONG, chunk_index: 0 },
          ],
          evaluation: { failure_type: 'RETRIEVAL_PARTIAL', used_llm_judge: false },
        }),
      )
      expect(lines.some((l) => l.key === 'failure-retrieval-partial')).toBe(true)
    })

    it('adds explicit line for CHUNK_FRAGMENTATION', () => {
      const lines = diagnosisSummaryFor(
        baseRun({
          retrieval_hits: [{ rank: 1, score: 0.6, chunk_id: 1, document_id: 1, content: LONG, chunk_index: 0 }],
          evaluation: { failure_type: 'CHUNK_FRAGMENTATION', used_llm_judge: false },
        }),
      )
      expect(lines.some((l) => l.key === 'failure-chunk-fragmentation')).toBe(true)
    })

    it('adds explicit line for CONTEXT_TRUNCATION', () => {
      const lines = diagnosisSummaryFor(
        baseRun({
          retrieval_hits: [{ rank: 1, score: 0.6, chunk_id: 1, document_id: 1, content: LONG, chunk_index: 0 }],
          evaluation: { failure_type: 'CONTEXT_TRUNCATION', used_llm_judge: false },
        }),
      )
      expect(lines.some((l) => l.key === 'failure-context-truncation')).toBe(true)
    })

    it('adds explicit line for MIXED_FAILURE', () => {
      const lines = diagnosisSummaryFor(
        baseRun({
          retrieval_hits: [{ rank: 1, score: 0.6, chunk_id: 1, document_id: 1, content: LONG, chunk_index: 0 }],
          evaluation: { failure_type: 'MIXED_FAILURE', used_llm_judge: false },
        }),
      )
      expect(lines.some((l) => l.key === 'failure-mixed')).toBe(true)
    })

    it('adds explicit neutral line for UNKNOWN instead of implying no issues', () => {
      const lines = diagnosisSummaryFor(
        baseRun({
          retrieval_hits: [{ rank: 1, score: 0.6, chunk_id: 1, document_id: 1, content: LONG, chunk_index: 0 }],
          evaluation: { failure_type: 'UNKNOWN', used_llm_judge: false, faithfulness: null },
        }),
      )
      expect(lines.some((l) => l.key === 'failure-unknown')).toBe(true)
      expect(lines.some((l) => l.key === 'ok')).toBe(false)
    })

    it('prefers generation bottleneck copy when answer failure but retrieval signals are usable', () => {
      const lines = diagnosisSummaryFor(
        baseRun({
          retrieval_hits: [
            { rank: 1, score: 0.5, chunk_id: 1, document_id: 1, content: LONG, chunk_index: 0 },
          ],
          evaluation: {
            failure_type: 'ANSWER_INCOMPLETE',
            used_llm_judge: false,
            faithfulness: 0.3,
            context_coverage: 0.7,
            retrieval_relevance: 0.5,
          },
        }),
      )
      expect(lines.some((l) => l.key === 'generation-likely')).toBe(true)
      expect(lines.some((l) => l.key === 'unsupported')).toBe(false)
    })

    it('keeps unsupported line when answer failure and retrieval is weak', () => {
      const lines = diagnosisSummaryFor(
        baseRun({
          retrieval_hits: [
            { rank: 1, score: 0.2, chunk_id: 1, document_id: 1, content: LONG, chunk_index: 0 },
          ],
          evaluation: {
            failure_type: 'ANSWER_UNSUPPORTED',
            used_llm_judge: false,
            retrieval_relevance: 0.2,
            faithfulness: 0.3,
          },
        }),
      )
      expect(lines.some((l) => l.key === 'generation-likely')).toBe(false)
      expect(lines.some((l) => l.key === 'unsupported')).toBe(true)
      expect(lines.some((l) => l.key === 'weak-retrieval')).toBe(true)
    })

    it('flags expensive-but-weak when cost is high and outcome is not clean', () => {
      const lines = diagnosisSummaryFor(
        baseRun({
          retrieval_hits: [{ rank: 1, score: 0.3, chunk_id: 1, document_id: 1, content: LONG, chunk_index: 0 }],
          evaluation: {
            failure_type: 'RETRIEVAL_PARTIAL',
            used_llm_judge: true,
            cost_usd: 0.009,
            faithfulness: 0.4,
            completeness: 0.4,
            retrieval_relevance: 0.4,
            context_coverage: 0.4,
          },
        }),
      )
      expect(lines.some((l) => l.key === 'expensive-weak')).toBe(true)
    })

    it('shows clean ok path when NO_FAILURE and signals are fine', () => {
      const lines = diagnosisSummaryFor(
        baseRun({
          retrieval_hits: [
            { rank: 1, score: 0.6, chunk_id: 1, document_id: 1, content: LONG, chunk_index: 0 },
            { rank: 2, score: 0.55, chunk_id: 2, document_id: 2, content: LONG, chunk_index: 0 },
          ],
          evaluation: {
            failure_type: 'NO_FAILURE',
            used_llm_judge: false,
            faithfulness: 0.8,
            completeness: 0.8,
            retrieval_relevance: 0.8,
            context_coverage: 0.8,
          },
        }),
      )
      expect(lines.some((l) => l.key === 'ok')).toBe(true)
      expect(lines.filter((l) => l.severity === 'attention')).toHaveLength(0)
    })
  })
})
