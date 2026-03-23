/** @vitest-environment jsdom */
import '@testing-library/jest-dom/vitest'
import { cleanup, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import type { LatencyDistributionSection } from '../api/types'
import { LatencyDistributionPanel } from './LatencyDistributionPanel'

const empty: LatencyDistributionSection['generation'] = {
  count: 0,
  min_ms: null,
  max_ms: null,
  avg_ms: null,
  median_ms: null,
  p95_ms: null,
}

describe('LatencyDistributionPanel', () => {
  afterEach(() => {
    cleanup()
  })

  it('uses exact insufficient-sample copy per phase and hides distribution details', () => {
    const data: LatencyDistributionSection = {
      retrieval: { count: 2, min_ms: 1, max_ms: 50, avg_ms: 20, median_ms: 18, p95_ms: 45 },
      generation: empty,
      evaluation: { count: 3, min_ms: 2, max_ms: 30, avg_ms: 10, median_ms: 9, p95_ms: 28 },
      total: { count: 5, min_ms: 20, max_ms: 200, avg_ms: 100, median_ms: 95, p95_ms: 180 },
    }
    render(<LatencyDistributionPanel data={data} />)
    expect(screen.getByTestId('latency-phase-insufficient-retrieval')).toHaveTextContent(
      'Insufficient samples for distribution (2 runs)',
    )
    expect(screen.getByTestId('latency-phase-insufficient-evaluation')).toHaveTextContent(
      'Insufficient samples for distribution (3 runs)',
    )
    expect(screen.queryByTestId('latency-phase-dl-retrieval')).not.toBeInTheDocument()
    expect(screen.queryByTestId('latency-phase-dl-evaluation')).not.toBeInTheDocument()
    expect(screen.getByTestId('latency-phase-dl-total')).toBeInTheDocument()
  })

  it('shows median vs average note when any phase has samples', () => {
    const data: LatencyDistributionSection = {
      retrieval: { count: 1, min_ms: 10, max_ms: 10, avg_ms: 10, median_ms: 10, p95_ms: 10 },
      generation: empty,
      evaluation: empty,
      total: empty,
    }
    render(<LatencyDistributionPanel data={data} />)
    const notes = screen.getAllByTestId('latency-median-vs-avg-note')
    expect(notes.length).toBeGreaterThanOrEqual(1)
    expect(notes[0]).toHaveTextContent(
      'Median is more representative than average when cold-start outliers are present.',
    )
  })

  it('orders detailed stats Median (P50) → P95 → Min → Max → Mean for sufficient samples', () => {
    const data: LatencyDistributionSection = {
      retrieval: { count: 5, min_ms: 1, max_ms: 50, avg_ms: 20, median_ms: 18, p95_ms: 45 },
      generation: empty,
      evaluation: empty,
      total: empty,
    }
    render(<LatencyDistributionPanel data={data} />)
    const dl = screen.getByTestId('latency-phase-dl-retrieval')
    const dts = within(dl).getAllByRole('term').map((el) => el.textContent ?? '')
    expect(dts).toEqual(['Count', 'Median (P50)', 'P95', 'Min', 'Max', 'Mean'])
    const phaseBlock = dl.closest('.cl-latency-phase-block')
    expect(phaseBlock).toBeTruthy()
    const bars = within(phaseBlock as HTMLElement).getByLabelText('Latency comparison within phase')
    const barLabels = [...bars.querySelectorAll('.cl-latency-hbar-label')].map((n) => n.textContent ?? '')
    expect(barLabels).toEqual(['Median (P50)', 'P95', 'Max'])
  })

  it('shows latency skew warning banner when any phase has data', () => {
    const data: LatencyDistributionSection = {
      retrieval: { count: 5, min_ms: 1, max_ms: 50, avg_ms: 20, median_ms: 18, p95_ms: 45 },
      generation: empty,
      evaluation: empty,
      total: empty,
    }
    render(<LatencyDistributionPanel data={data} />)
    expect(screen.getByTestId('latency-skew-warning')).toHaveTextContent(
      /Latency is highly skewed due to local execution and cold-start effects/,
    )
    expect(screen.getByTestId('latency-skew-warning')).toHaveTextContent(
      /not SLA-grade measurements/,
    )
  })

  it('shows high variance badge when P95/P50 ratio > 10', () => {
    const data: LatencyDistributionSection = {
      retrieval: { count: 53, min_ms: 9, max_ms: 6222, avg_ms: 270, median_ms: 18, p95_ms: 1471 },
      generation: empty,
      evaluation: empty,
      total: empty,
    }
    render(<LatencyDistributionPanel data={data} />)
    expect(screen.getByTestId('latency-high-variance-retrieval')).toHaveTextContent(
      'High variance (skewed distribution)',
    )
  })

  it('does not show high variance badge when P95/P50 ratio <= 10', () => {
    const data: LatencyDistributionSection = {
      retrieval: { count: 53, min_ms: 10, max_ms: 100, avg_ms: 50, median_ms: 40, p95_ms: 90 },
      generation: empty,
      evaluation: empty,
      total: empty,
    }
    render(<LatencyDistributionPanel data={data} />)
    expect(screen.queryByTestId('latency-high-variance-retrieval')).not.toBeInTheDocument()
  })

  it('shows low sample badge when count < 20 but >= 5', () => {
    const data: LatencyDistributionSection = {
      retrieval: empty,
      generation: { count: 5, min_ms: 100, max_ms: 500, avg_ms: 300, median_ms: 280, p95_ms: 450 },
      evaluation: empty,
      total: empty,
    }
    render(<LatencyDistributionPanel data={data} />)
    expect(screen.getByTestId('latency-low-sample-generation')).toHaveTextContent(
      'Low sample (5) — not reliable',
    )
  })

  it('does not show low sample badge when count >= 20', () => {
    const data: LatencyDistributionSection = {
      retrieval: { count: 25, min_ms: 1, max_ms: 50, avg_ms: 20, median_ms: 18, p95_ms: 45 },
      generation: empty,
      evaluation: empty,
      total: empty,
    }
    render(<LatencyDistributionPanel data={data} />)
    expect(screen.queryByTestId('latency-low-sample-retrieval')).not.toBeInTheDocument()
  })
})
