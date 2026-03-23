/**
 * Run-detail diagnosis helpers — derive beginner-friendly signals from `GET /runs/{id}` payload.
 * No React; unit-testable.
 */

import type { RunDetail } from '../api/types'
import { formatScore } from './dashboardAnalyticsFormat'

export type RetrievalHit = RunDetail['retrieval_hits'][number]

export type RetrievalDiagnosisModel = {
  hitCount: number
  topScore: number | null
  rank1MinusRank2: number | null
  interpretations: string[]
}

/** Cosine-style scores are in ~[0,1]; tune thresholds conservatively for demos. */
const LOW_TOP_SCORE = 0.38
const TIGHT_GAP = 0.025

/** When ≥3 hits all share the same document_id, warn about weak source diversity (no titles; IDs only in payload). */
function retrievalSourceConcentrationInterpretation(hits: RetrievalHit[]): string | null {
  const sorted = [...hits].sort((a, b) => a.rank - b.rank)
  if (sorted.length < 3) return null
  const firstId = sorted[0]?.document_id
  if (firstId == null) return null
  const allSame = sorted.every((h) => h.document_id === firstId)
  if (!allSame) return null
  return (
    'All retrieved chunks in this list share the same document — source diversity may be weak, so overlapping ' +
    'or repetitive evidence can dominate the context window.'
  )
}

export function computeRetrievalDiagnosis(hits: RetrievalHit[]): RetrievalDiagnosisModel {
  const sorted = [...hits].sort((a, b) => a.rank - b.rank)
  const n = sorted.length
  const top = sorted[0]
  const second = sorted[1]
  const topScore = top != null ? top.score : null
  const rank1MinusRank2 =
    top != null && second != null ? Math.max(0, top.score - second.score) : null

  const interpretations: string[] = []
  if (n === 0) {
    interpretations.push('No chunks were retrieved — check corpus, embeddings, or query wording.')
  } else {
    interpretations.push(
      `Retrieved ${n} chunk(s). Top match score ${topScore != null ? topScore.toFixed(3) : 'N/A'} (higher is more similar to the query embedding).`,
    )
    if (topScore != null && topScore < LOW_TOP_SCORE) {
      interpretations.push(
        'Top score is fairly low — the best match may still be a weak semantic fit.',
      )
    }
    if (rank1MinusRank2 != null && second != null) {
      if (rank1MinusRank2 < TIGHT_GAP) {
        interpretations.push(
          'Rank #1 and #2 are very close in score — the ordering is fragile; consider top_k or reranking.',
        )
      } else {
        interpretations.push(
          `Clear gap (${rank1MinusRank2.toFixed(3)}) between #1 and #2 — the top chunk stands out more strongly.`,
        )
      }
    } else if (n === 1) {
      interpretations.push('Only one hit returned — compare with pipeline top_k and corpus size.')
    }
    const concentration = retrievalSourceConcentrationInterpretation(sorted)
    if (concentration) interpretations.push(concentration)
  }

  return { hitCount: n, topScore, rank1MinusRank2, interpretations }
}

export type ContextChunkRow = { rank: number; lengthChars: number }

export type ContextQualityModel = {
  chunkRows: ContextChunkRow[]
  totalChars: number
  avgChars: number | null
  thinContext: boolean
  sparseContext: boolean
  repetitiveWarning: string | null
  notes: string[]
}

const THIN_AVG_CHARS = 120
const THIN_TOTAL_CHARS = 450

/** Prefix / suffix–prefix overlap must reach this length to flag (chars after normalize). */
const CHUNK_OVERLAP_MIN_CHARS = 80
const CHUNK_OVERLAP_SCAN_CAP = 240

function normalizeChunkBody(s: string): string {
  return s.replace(/\s+/g, ' ').trim().toLowerCase()
}

/**
 * True when retrieved count is below pipeline top_k in a way that is suspicious even for small top_k.
 * Rule: zero hits; or fewer hits than top_k while count is at or below ceil(top_k/3) (e.g. 1 of 2–3, 1–2 of 5–6).
 */
function computeSparseContextFlag(hitCount: number, topK: number): boolean {
  if (hitCount === 0) return true
  if (topK <= 1) return false
  if (hitCount >= topK) return false
  const cap = Math.max(1, Math.ceil(topK / 3))
  return hitCount <= cap
}

function longestSuffixPrefixOverlapLen(a: string, b: string): number {
  const lim = Math.min(a.length, b.length, CHUNK_OVERLAP_SCAN_CAP)
  for (let k = lim; k >= CHUNK_OVERLAP_MIN_CHARS; k--) {
    if (a.slice(-k) === b.slice(0, k)) return k
  }
  return 0
}

export function computeContextQuality(
  hits: RetrievalHit[],
  topK: number,
): ContextQualityModel {
  const sorted = [...hits].sort((a, b) => a.rank - b.rank)
  const chunkRows: ContextChunkRow[] = sorted.map((h) => ({
    rank: h.rank,
    lengthChars: (h.content ?? '').length,
  }))
  const totalChars = chunkRows.reduce((s, r) => s + r.lengthChars, 0)
  const avgChars = chunkRows.length ? totalChars / chunkRows.length : null

  const thinContext =
    chunkRows.length > 0 &&
    (totalChars < THIN_TOTAL_CHARS || (avgChars != null && avgChars < THIN_AVG_CHARS))

  const sparseContext = computeSparseContextFlag(chunkRows.length, topK)

  const norms = sorted.map((h) => normalizeChunkBody(h.content ?? ''))
  const uniq = new Set(norms.filter((x) => x.length > 0))
  let repetitiveWarning: string | null = null
  if (norms.length >= 2 && uniq.size < norms.length) {
    repetitiveWarning =
      'Some retrieved chunks are duplicates or near-duplicates — context may be repetitive.'
  } else if (norms.length >= 2) {
    // Longest common prefix heuristic across first two chunks
    const [a, b] = [norms[0], norms[1]]
    let i = 0
    const lim = Math.min(a.length, b.length, 200)
    while (i < lim && a[i] === b[i]) i++
    if (i >= CHUNK_OVERLAP_MIN_CHARS) {
      repetitiveWarning =
        'Top chunks share a long identical prefix — snippets may be overlapping or redundant.'
    }
    // Consecutive chunks: suffix of chunk i matches prefix of chunk i+1 (recursive overlap / sliding window)
    if (repetitiveWarning == null) {
      for (let idx = 0; idx < norms.length - 1; idx++) {
        const o = longestSuffixPrefixOverlapLen(norms[idx], norms[idx + 1])
        if (o >= CHUNK_OVERLAP_MIN_CHARS) {
          repetitiveWarning =
            'Neighboring chunks share a long tail/head overlap — text may be duplicated across chunk boundaries.'
          break
        }
      }
    }
  }

  const notes: string[] = []
  if (thinContext) {
    notes.push(
      'Context volume is small — answers may lack detail or cite thin evidence.',
    )
  }
  if (sparseContext && chunkRows.length > 0) {
    notes.push(
      `Fewer chunks than pipeline top_k (${topK}) — index or filters may be limiting recall.`,
    )
  }
  if (chunkRows.length === 0) {
    notes.push('No chunk text to analyze.')
  }

  return {
    chunkRows,
    totalChars,
    avgChars,
    thinContext,
    sparseContext,
    repetitiveWarning,
    notes,
  }
}

export type DiagnosisBadge = { key: string; label: string; tone: 'warn' | 'info' }

export type GenerationJudgeInsightsModel = {
  generationModel: string | null
  judgeModel: string | null
  genInputTokens: number | null
  genOutputTokens: number | null
  judgeInputTokens: number | null
  judgeOutputTokens: number | null
  totalCostUsd: number | null
  badges: DiagnosisBadge[]
}

function num(v: unknown): number | null {
  if (typeof v === 'number' && Number.isFinite(v)) return v
  if (typeof v === 'string' && v.trim() !== '' && Number.isFinite(Number(v))) return Number(v)
  return null
}

function bool(v: unknown): boolean | undefined {
  if (typeof v === 'boolean') return v
  return undefined
}

function str(v: unknown): string | null {
  if (typeof v === 'string' && v.trim() !== '') return v
  return null
}

export function extractGenerationJudgeInsights(
  generation: Record<string, unknown> | null,
  evaluation: Record<string, unknown> | null,
): GenerationJudgeInsightsModel {
  const genMeta =
    generation && typeof generation.metadata_json === 'object' && generation.metadata_json !== null
      ? (generation.metadata_json as Record<string, unknown>)
      : null
  const evMeta =
    evaluation && typeof evaluation.metadata_json === 'object' && evaluation.metadata_json !== null
      ? (evaluation.metadata_json as Record<string, unknown>)
      : null

  const generationModel = generation ? str(generation.model_id) : null
  const judgeModel = evMeta ? str(evMeta.judge_model) : null

  const genInputTokens = generation ? num(generation.input_tokens) : null
  const genOutputTokens = generation ? num(generation.output_tokens) : null

  let judgeInputTokens = evMeta ? num(evMeta.judge_input_tokens) : null
  let judgeOutputTokens = evMeta ? num(evMeta.judge_output_tokens) : null
  if (evaluation && judgeInputTokens == null) judgeInputTokens = num(evaluation.judge_input_tokens)
  if (evaluation && judgeOutputTokens == null) judgeOutputTokens = num(evaluation.judge_output_tokens)

  const totalCostUsd = evaluation ? num(evaluation.cost_usd) : null

  const badges: DiagnosisBadge[] = []

  if (evMeta) {
    const parseOk = bool(evMeta.judge_parse_ok)
    const retryAttempted = bool(evMeta.judge_retry_attempted)
    const retrySucceeded = bool(evMeta.judge_retry_succeeded)
    const warnings = evMeta.judge_parse_warnings

    if (parseOk === false) {
      badges.push({
        key: 'parse-fail',
        label: 'Judge JSON parse had issues',
        tone: 'warn',
      })
    }
    if (retryAttempted === true && retrySucceeded === false) {
      badges.push({
        key: 'retry-fail',
        label: 'Judge retry still could not parse cleanly',
        tone: 'warn',
      })
    } else if (retryAttempted === true && retrySucceeded === true) {
      badges.push({
        key: 'retry-ok',
        label: 'Judge needed a second parse attempt',
        tone: 'info',
      })
    }

    if (Array.isArray(warnings) && warnings.length > 0) {
      const first = warnings.find((w) => typeof w === 'string') as string | undefined
      badges.push({
        key: 'parse-warnings',
        label: first
          ? `Parse notes: ${String(first)}${warnings.length > 1 ? ` (+${warnings.length - 1} more)` : ''}`
          : `Parse warnings recorded (${warnings.length})`,
        tone: 'warn',
      })
    }
  }

  if (genMeta?.provider != null && typeof genMeta.provider === 'string') {
    badges.push({
      key: 'gen-provider',
      label: `Generation provider: ${String(genMeta.provider)}`,
      tone: 'info',
    })
  }

  return {
    generationModel,
    judgeModel,
    genInputTokens,
    genOutputTokens,
    judgeInputTokens,
    judgeOutputTokens,
    totalCostUsd,
    badges,
  }
}

export type DiagnosisSummaryLine = { key: string; text: string; severity: 'attention' | 'neutral' }

/** Explicit summary lines for taxonomy values that previously had no tailored copy (avoid a false “all clear”). */
const FAILURE_TAXONOMY_SUMMARY: Partial<Record<string, DiagnosisSummaryLine>> = {
  CONTEXT_INSUFFICIENT: {
    key: 'failure-context-insufficient',
    text: 'Failure type CONTEXT_INSUFFICIENT — retrieved chunks do not cover enough of the query (low context coverage vs query terms).',
    severity: 'attention',
  },
  RETRIEVAL_PARTIAL: {
    key: 'failure-retrieval-partial',
    text: 'Failure type RETRIEVAL_PARTIAL — some evidence was retrieved but it may be thin or not enough to answer reliably.',
    severity: 'attention',
  },
  CHUNK_FRAGMENTATION: {
    key: 'failure-chunk-fragmentation',
    text: 'Failure type CHUNK_FRAGMENTATION — evidence may be split across awkward chunk boundaries; review chunking and top_k.',
    severity: 'attention',
  },
  CONTEXT_TRUNCATION: {
    key: 'failure-context-truncation',
    text: 'Failure type CONTEXT_TRUNCATION — the assembled context may have been cut off before the model saw full evidence.',
    severity: 'attention',
  },
  MIXED_FAILURE: {
    key: 'failure-mixed',
    text: 'Failure type MIXED_FAILURE — multiple weak signals together; inspect retrieval, context volume, and generation scores.',
    severity: 'attention',
  },
  UNKNOWN: {
    key: 'failure-unknown',
    text: 'Failure type UNKNOWN — the evaluator could not classify this run cleanly; treat scores as hints and review manually.',
    severity: 'neutral',
  },
}

export function computeRunDiagnosisSummary(
  detail: RunDetail,
  retrieval: RetrievalDiagnosisModel,
  contextQ: ContextQualityModel,
  genJudge: GenerationJudgeInsightsModel,
): DiagnosisSummaryLine[] {
  const lines: DiagnosisSummaryLine[] = []
  const ev = detail.evaluation
  const failureType = ev && typeof ev.failure_type === 'string' ? ev.failure_type : null
  const numScore = (k: string): number | null => {
    if (!ev || typeof ev !== 'object') return null
    return num((ev as Record<string, unknown>)[k])
  }
  const retrievalRel = numScore('retrieval_relevance')
  const contextCov = numScore('context_coverage')
  const faithfulness = numScore('faithfulness')
  const completeness = numScore('completeness')

  const taxonomyLine = failureType ? FAILURE_TAXONOMY_SUMMARY[failureType] : undefined
  if (taxonomyLine) {
    lines.push(taxonomyLine)
  }

  if (retrieval.hitCount === 0 || failureType === 'RETRIEVAL_MISS') {
    lines.push({
      key: 'retrieval',
      text: 'Likely retrieval issue — no usable chunks or explicit RETRIEVAL_MISS.',
      severity: 'attention',
    })
  } else if (
    retrieval.topScore != null &&
    retrieval.topScore < LOW_TOP_SCORE &&
    (retrievalRel == null || retrievalRel < 0.45)
  ) {
    lines.push({
      key: 'weak-retrieval',
      text: 'Likely weak retrieval — low top similarity and weak relevance signal.',
      severity: 'attention',
    })
  }

  const isAnswerQualityFailure =
    failureType === 'ANSWER_UNSUPPORTED' || failureType === 'ANSWER_INCOMPLETE'
  const retrievalReasonable =
    retrieval.hitCount > 0 &&
    ((retrieval.topScore != null && retrieval.topScore >= LOW_TOP_SCORE) ||
      (retrievalRel != null && retrievalRel >= 0.45))

  if (isAnswerQualityFailure && retrievalReasonable) {
    lines.push({
      key: 'generation-likely',
      text:
        failureType === 'ANSWER_INCOMPLETE'
          ? 'Judge flagged an incomplete answer while retrieval signals look usable — generation or summarization may be the bottleneck, not recall.'
          : 'Judge flagged an unsupported answer while retrieval signals look usable — generation may be drifting off the evidence or over-asserting.',
      severity: 'attention',
    })
  } else if (
    failureType === 'ANSWER_UNSUPPORTED' ||
    failureType === 'ANSWER_INCOMPLETE' ||
    (faithfulness != null && faithfulness < 0.45 && contextCov != null && contextCov >= 0.5)
  ) {
    lines.push({
      key: 'unsupported',
      text: 'Possible unsupported or thin answer vs context — check failure type and faithfulness.',
      severity: 'attention',
    })
  }

  if (contextCov != null && contextCov < 0.42) {
    lines.push({
      key: 'low-coverage',
      text: 'Low context coverage — retrieved text may not contain enough query terms/evidence.',
      severity: 'attention',
    })
  }

  if (contextQ.thinContext && retrieval.hitCount > 0) {
    lines.push({
      key: 'thin',
      text: 'Thin context — short chunks limit what the model can cite.',
      severity: 'neutral',
    })
  }

  const cost = genJudge.totalCostUsd
  const weakScores = [faithfulness, completeness, retrievalRel, contextCov].filter(
    (x): x is number => x != null,
  )
  const avgWeak =
    weakScores.length > 0 ? weakScores.reduce((a, b) => a + b, 0) / weakScores.length : null
  if (
    cost != null &&
    cost >= 0.008 &&
    failureType != null &&
    failureType !== 'NO_FAILURE' &&
    (avgWeak == null || avgWeak < 0.55)
  ) {
    lines.push({
      key: 'expensive-weak',
      text: 'Paid LLM cost is non-trivial but the outcome still looks weak — tune retrieval or prompts.',
      severity: 'attention',
    })
  }

  if (lines.length === 0) {
    lines.push({
      key: 'ok',
      text: 'No strong automatic red flags — review scores and failure type below for nuance.',
      severity: 'neutral',
    })
  }

  return lines
}

/** Display rows for evaluation scores + labels (same API fields as `EvaluationOut`). */
export type EvaluationScoreRow = { label: string; value: string; emphasize?: boolean }

function fmtEvalNumber(v: unknown): string {
  if (v == null) return 'N/A'
  const n = typeof v === 'number' ? v : Number(v)
  if (Number.isNaN(n)) return 'N/A'
  return formatScore(n)
}

export function evaluationScoreRows(
  evaluation: Record<string, unknown> | null,
): EvaluationScoreRow[] {
  if (!evaluation || typeof evaluation !== 'object') return []

  const ev = evaluation as Record<string, unknown>
  const rows: EvaluationScoreRow[] = [
    { label: 'Faithfulness', value: fmtEvalNumber(ev.faithfulness) },
    { label: 'Completeness', value: fmtEvalNumber(ev.completeness) },
    { label: 'Retrieval relevance', value: fmtEvalNumber(ev.retrieval_relevance) },
    { label: 'Context coverage', value: fmtEvalNumber(ev.context_coverage) },
    { label: 'Groundedness', value: fmtEvalNumber(ev.groundedness) },
    {
      label: 'Failure type',
      value: ev.failure_type != null && String(ev.failure_type).trim() !== '' ? String(ev.failure_type) : 'N/A',
      emphasize: true,
    },
    {
      label: 'LLM judge used',
      value:
        ev.used_llm_judge === true ? 'yes' : ev.used_llm_judge === false ? 'no' : 'N/A',
    },
  ]
  return rows
}
