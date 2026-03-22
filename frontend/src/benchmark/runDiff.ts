/**
 * Deterministic run-vs-run comparison for `GET /runs/{id}` payloads.
 * Reuses `runDiagnosis` primitives where applicable (no duplicated retrieval/context math).
 */

import type { RunDetail } from '../api/types'
import { formatScore } from './dashboardAnalyticsFormat'
import { formatUsd } from './dashboardFormat'
import {
  computeContextQuality,
  computeRetrievalDiagnosis,
  extractGenerationJudgeInsights,
} from './runDiagnosis'

/** B relative to A: improved = B better, worse = B worse, same = tie, unknown = can’t tell. */
export type DiffVerdict = 'improved' | 'worse' | 'same' | 'unknown'

export type RunDiffRow = {
  id: string
  label: string
  aValue: string
  bValue: string
  verdict: DiffVerdict
}

export type RunDiffModel = {
  baseRunId: number
  compareRunId: number
  warnings: string[]
  summaryLines: string[]
  rows: RunDiffRow[]
}

const EPS = 1e-6

export function compareNumbers(
  a: number | null | undefined,
  b: number | null | undefined,
  higherIsBetter: boolean,
): DiffVerdict {
  if (a == null || b == null || !Number.isFinite(a) || !Number.isFinite(b)) return 'unknown'
  if (Math.abs(a - b) <= EPS) return 'same'
  if (higherIsBetter) return b > a ? 'improved' : 'worse'
  return b < a ? 'improved' : 'worse'
}

function evNum(ev: Record<string, unknown> | null, key: string): number | null {
  if (!ev || typeof ev !== 'object') return null
  const v = ev[key]
  if (typeof v === 'number' && Number.isFinite(v)) return v
  if (typeof v === 'string' && v.trim() !== '' && Number.isFinite(Number(v))) return Number(v)
  return null
}

function evFailure(ev: Record<string, unknown> | null): string | null {
  if (!ev || typeof ev !== 'object') return null
  const f = ev.failure_type
  if (f == null || f === '') return null
  return String(f)
}

export function compareFailureTypes(a: string | null, b: string | null): DiffVerdict {
  const good = (t: string | null) => t === 'NO_FAILURE'
  if (a == null && b == null) return 'unknown'
  if (a === b) return 'same'
  if (good(b) && !good(a)) return 'improved'
  if (good(a) && !good(b)) return 'worse'
  return 'unknown'
}

export function compareLifecycleStatus(a: string, b: string): DiffVerdict {
  if (a === b) return 'same'
  if (a === 'completed' && b === 'failed') return 'worse'
  if (a === 'failed' && b === 'completed') return 'improved'
  if (a === 'completed' && b !== 'completed' && b !== 'failed') return 'unknown'
  if (b === 'completed' && a !== 'completed' && a !== 'failed') return 'unknown'
  return 'unknown'
}

function hasGenerationAnswer(gen: Record<string, unknown> | null): boolean {
  return (
    gen != null &&
    typeof gen === 'object' &&
    typeof gen.answer_text === 'string' &&
    gen.answer_text.trim().length > 0
  )
}

function fmt(n: number | null, digits = 4): string {
  if (n == null || !Number.isFinite(n)) return 'Unknown'
  return n.toFixed(digits)
}

function fmtScore(n: number | null): string {
  if (n == null || !Number.isFinite(n)) return 'Unknown'
  return formatScore(n)
}

export function buildRunDiffModel(base: RunDetail, compare: RunDetail): RunDiffModel {
  const warnings: string[] = []
  if (base.query_case.id !== compare.query_case.id) {
    warnings.push(
      'These runs use different query cases — compare trends only; answers are not for the same question text.',
    )
  }
  if (base.pipeline_config.id !== compare.pipeline_config.id) {
    warnings.push('Pipeline configs differ — retrieval and scoring are not apples-to-apples.')
  }

  const rA = computeRetrievalDiagnosis(base.retrieval_hits)
  const rB = computeRetrievalDiagnosis(compare.retrieval_hits)
  const cA = computeContextQuality(base.retrieval_hits, base.pipeline_config.top_k)
  const cB = computeContextQuality(compare.retrieval_hits, compare.pipeline_config.top_k)

  const gA = extractGenerationJudgeInsights(base.generation, base.evaluation)
  const gB = extractGenerationJudgeInsights(compare.generation, compare.evaluation)

  const baseEv = base.evaluation as Record<string, unknown> | null
  const cmpEv = compare.evaluation as Record<string, unknown> | null

  const rows: RunDiffRow[] = []

  rows.push({
    id: 'lifecycle',
    label: 'Run status',
    aValue: base.status,
    bValue: compare.status,
    verdict: compareLifecycleStatus(base.status, compare.status),
  })

  rows.push({
    id: 'retrieval_hits',
    label: 'Retrieval hit count',
    aValue: String(rA.hitCount),
    bValue: String(rB.hitCount),
    verdict: compareNumbers(rA.hitCount, rB.hitCount, true),
  })

  rows.push({
    id: 'top_score',
    label: 'Top retrieval score',
    aValue: fmt(rA.topScore),
    bValue: fmt(rB.topScore),
    verdict: compareNumbers(rA.topScore, rB.topScore, true),
  })

  rows.push({
    id: 'rank_gap',
    label: 'Rank 1 − rank 2 score gap',
    aValue: fmt(rA.rank1MinusRank2),
    bValue: fmt(rB.rank1MinusRank2),
    verdict: compareNumbers(rA.rank1MinusRank2, rB.rank1MinusRank2, true),
  })

  rows.push({
    id: 'context_chunks',
    label: 'Context chunks (count)',
    aValue: String(cA.chunkRows.length),
    bValue: String(cB.chunkRows.length),
    verdict: compareNumbers(cA.chunkRows.length, cB.chunkRows.length, true),
  })

  rows.push({
    id: 'context_chars',
    label: 'Total context characters',
    aValue: String(cA.totalChars),
    bValue: String(cB.totalChars),
    verdict: compareNumbers(cA.totalChars, cB.totalChars, true),
  })

  const thinVerdict: DiffVerdict =
    cA.chunkRows.length === 0 || cB.chunkRows.length === 0
      ? 'unknown'
      : cA.thinContext && !cB.thinContext
        ? 'improved'
        : !cA.thinContext && cB.thinContext
          ? 'worse'
          : 'same'
  rows.push({
    id: 'thin_context',
    label: 'Thin context heuristic',
    aValue: cA.chunkRows.length ? (cA.thinContext ? 'Yes (thin)' : 'No') : 'Unknown',
    bValue: cB.chunkRows.length ? (cB.thinContext ? 'Yes (thin)' : 'No') : 'Unknown',
    verdict: thinVerdict,
  })

  const aGen = hasGenerationAnswer(base.generation as Record<string, unknown> | null)
  const bGen = hasGenerationAnswer(compare.generation as Record<string, unknown> | null)
  let genVerdict: DiffVerdict = 'unknown'
  if (aGen === bGen) genVerdict = 'same'
  else if (!aGen && bGen) genVerdict = 'improved'
  else if (aGen && !bGen) genVerdict = 'worse'
  rows.push({
    id: 'generation_answer',
    label: 'Generated answer present',
    aValue: aGen ? 'Yes' : 'No',
    bValue: bGen ? 'Yes' : 'No',
    verdict: genVerdict,
  })

  const tokA = gA.genOutputTokens
  const tokB = gB.genOutputTokens
  rows.push({
    id: 'gen_output_tokens',
    label: 'Generation output tokens',
    aValue: tokA != null ? String(tokA) : 'Unknown',
    bValue: tokB != null ? String(tokB) : 'Unknown',
    verdict: 'unknown',
  })

  rows.push({
    id: 'cost_usd',
    label: 'Evaluation cost (USD)',
    aValue: formatUsd(gA.totalCostUsd),
    bValue: formatUsd(gB.totalCostUsd),
    verdict: compareNumbers(gA.totalCostUsd, gB.totalCostUsd, false),
  })

  const fA = evFailure(baseEv)
  const fB = evFailure(cmpEv)
  rows.push({
    id: 'failure_type',
    label: 'Failure type',
    aValue: fA ?? 'Unknown',
    bValue: fB ?? 'Unknown',
    verdict: compareFailureTypes(fA, fB),
  })

  for (const key of ['retrieval_relevance', 'context_coverage', 'faithfulness', 'completeness'] as const) {
    const nA = evNum(baseEv, key)
    const nB = evNum(cmpEv, key)
    const label =
      key === 'retrieval_relevance'
        ? 'Retrieval relevance (eval)'
        : key === 'context_coverage'
          ? 'Context coverage (eval)'
          : key === 'faithfulness'
            ? 'Faithfulness'
            : 'Completeness'
    rows.push({
      id: key,
      label,
      aValue: fmtScore(nA),
      bValue: fmtScore(nB),
      verdict: compareNumbers(nA, nB, true),
    })
  }

  const summaryLines = buildDiffSummaryLines(rows, warnings, gA.totalCostUsd, gB.totalCostUsd)

  return {
    baseRunId: base.run_id,
    compareRunId: compare.run_id,
    warnings,
    summaryLines,
    rows,
  }
}

export function verdictLabel(v: DiffVerdict): string {
  switch (v) {
    case 'improved':
      return 'B better'
    case 'worse':
      return 'B worse'
    case 'same':
      return 'Same'
    default:
      return 'Unknown'
  }
}

function buildDiffSummaryLines(
  rows: RunDiffRow[],
  warnings: string[],
  costA: number | null,
  costB: number | null,
): string[] {
  const lines: string[] = []
  const get = (id: string) => rows.find((r) => r.id === id)

  const hits = get('retrieval_hits')
  const top = get('top_score')
  if (hits?.verdict === 'improved' || top?.verdict === 'improved') {
    lines.push('Run B has stronger retrieval signals (more hits and/or a higher top score).')
  } else if (hits?.verdict === 'worse' || top?.verdict === 'worse') {
    lines.push('Run B shows weaker retrieval than run A.')
  }

  const thin = get('thin_context')
  if (thin?.verdict === 'improved') {
    lines.push('Run B moves away from “thin” context vs run A.')
  } else if (thin?.verdict === 'worse') {
    lines.push('Run B looks thinner on context volume than run A.')
  }

  const fail = get('failure_type')
  if (fail?.verdict === 'improved') {
    lines.push('Run B has a cleaner failure label (closer to NO_FAILURE).')
  } else if (fail?.verdict === 'worse') {
    lines.push('Run B shows a worse failure label than run A.')
  }

  const faith = get('faithfulness')
  const cov = get('context_coverage')
  if (faith?.verdict === 'improved' || cov?.verdict === 'improved') {
    lines.push('Run B scores higher on at least one key evaluation metric.')
  } else if (faith?.verdict === 'worse' || cov?.verdict === 'worse') {
    lines.push('Run B scores lower on at least one key evaluation metric.')
  }

  if (
    costA != null &&
    costB != null &&
    costB > costA + 1e-9 &&
    lines.every((l) => !/cost/i.test(l))
  ) {
    lines.push('Run B records higher evaluation cost — weigh against quality gains above.')
  }

  if (lines.length === 0) {
    lines.push(
      'No strong automatic differences detected on the rows below — inspect values manually.',
    )
  }

  if (warnings.length > 0) {
    lines.push('Note: configuration or query mismatch — treat this diff as directional, not exact.')
  }

  return lines.slice(0, 5)
}
