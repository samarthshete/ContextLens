/** @vitest-environment jsdom */
import '@testing-library/jest-dom/vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { RunsFilterBar } from './RunsFilterBar'
import { RUNS_LIST_FILTERS_INIT } from './runsListQuery'

afterEach(() => {
  cleanup()
})

describe('RunsFilterBar', () => {
  it('renders filter controls', () => {
    render(
      <RunsFilterBar
        values={RUNS_LIST_FILTERS_INIT}
        narrowText=""
        onChange={vi.fn()}
        onNarrowTextChange={vi.fn()}
        onClear={vi.fn()}
        datasets={[{ id: 1, name: 'D', description: null, created_at: 't' }]}
        pipelineConfigs={[
          {
            id: 2,
            name: 'P',
            embedding_model: 'm',
            chunk_strategy: 'fixed',
            chunk_size: 256,
            chunk_overlap: 0,
            top_k: 5,
            created_at: 't',
          },
        ]}
      />,
    )
    expect(screen.getByTestId('runs-filter-bar')).toBeInTheDocument()
    expect(screen.getByTestId('runs-filter-status')).toBeInTheDocument()
    expect(screen.getByTestId('runs-filter-evaluator')).toBeInTheDocument()
    expect(screen.getByTestId('runs-filter-dataset')).toBeInTheDocument()
    expect(screen.getByTestId('runs-filter-pipeline')).toBeInTheDocument()
    expect(screen.getByTestId('runs-filter-narrow')).toBeInTheDocument()
  })

  it('clear is disabled until something is set', () => {
    render(
      <RunsFilterBar
        values={RUNS_LIST_FILTERS_INIT}
        narrowText=""
        onChange={vi.fn()}
        onNarrowTextChange={vi.fn()}
        onClear={vi.fn()}
        datasets={[]}
        pipelineConfigs={[]}
      />,
    )
    expect(screen.getByTestId('runs-filter-clear')).toBeDisabled()
  })

  it('calls onChange when status changes', () => {
    const onChange = vi.fn()
    render(
      <RunsFilterBar
        values={RUNS_LIST_FILTERS_INIT}
        narrowText=""
        onChange={onChange}
        onNarrowTextChange={vi.fn()}
        onClear={vi.fn()}
        datasets={[]}
        pipelineConfigs={[]}
      />,
    )
    fireEvent.change(screen.getByTestId('runs-filter-status'), { target: { value: 'completed' } })
    expect(onChange).toHaveBeenCalledWith({ status: 'completed' })
  })

  it('calls onClear when clear clicked', () => {
    const onClear = vi.fn()
    render(
      <RunsFilterBar
        values={{ ...RUNS_LIST_FILTERS_INIT, status: 'failed' }}
        narrowText=""
        onChange={vi.fn()}
        onNarrowTextChange={vi.fn()}
        onClear={onClear}
        datasets={[]}
        pipelineConfigs={[]}
      />,
    )
    fireEvent.click(screen.getByTestId('runs-filter-clear'))
    expect(onClear).toHaveBeenCalled()
  })
})
