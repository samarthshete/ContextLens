// @vitest-environment jsdom
import { describe, it, expect, afterEach } from 'vitest'
import { render, screen, cleanup } from '@testing-library/react'
import { PhaseTimeline } from './PhaseTimeline'
import type { RunDetail } from '../api/types'

afterEach(() => cleanup())

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

describe('PhaseTimeline', () => {
  it('renders phase timeline with heuristic run', () => {
    render(<PhaseTimeline runDetail={baseRun()} />)
    expect(screen.getByTestId('phase-timeline')).toBeTruthy()
    expect(screen.getByTestId('timeline-retrieval')).toBeTruthy()
    expect(screen.getByTestId('timeline-evaluation')).toBeTruthy()
    expect(screen.getByTestId('timeline-total')).toBeTruthy()
    // Generation should show dash for unavailable
    const genRow = screen.getByTestId('timeline-generation')
    expect(genRow.textContent).toContain('—')
  })

  it('renders dominant phase for full run', () => {
    render(
      <PhaseTimeline
        runDetail={baseRun({
          retrieval_latency_ms: 120,
          generation_latency_ms: 3100,
          evaluation_latency_ms: 900,
          total_latency_ms: 4120,
        })}
      />,
    )
    // Generation should be marked dominant
    const genRow = screen.getByTestId('timeline-generation')
    expect(genRow.className).toContain('cl-timeline-dominant')
    // Summary mentions generation
    expect(screen.getByText(/Generation dominated/)).toBeTruthy()
  })

  it('returns null when no timing data', () => {
    const { container } = render(
      <PhaseTimeline
        runDetail={baseRun({
          retrieval_latency_ms: null,
          generation_latency_ms: null,
          evaluation_latency_ms: null,
          total_latency_ms: null,
        })}
      />,
    )
    expect(container.querySelector('[data-testid="phase-timeline"]')).toBeNull()
  })

  it('shows percentages only when valid', () => {
    render(
      <PhaseTimeline
        runDetail={baseRun({
          retrieval_latency_ms: 100,
          generation_latency_ms: 300,
          evaluation_latency_ms: 50,
          total_latency_ms: 400,
        })}
      />,
    )
    // Component sum (450) > total (400) — no percentages
    const retRow = screen.getByTestId('timeline-retrieval')
    expect(retRow.textContent).not.toContain('%')
  })
})
