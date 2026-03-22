import type { Dataset, PipelineConfig } from '../api/types'
import { RUN_FILTER_STATUS_VALUES, type RunsListServerFilters } from './runsListQuery'

export type RunsFilterBarProps = {
  values: RunsListServerFilters
  narrowText: string
  onChange: (next: Partial<RunsListServerFilters>) => void
  onNarrowTextChange: (text: string) => void
  onClear: () => void
  datasets: Dataset[]
  pipelineConfigs: PipelineConfig[]
}

export function RunsFilterBar({
  values,
  narrowText,
  onChange,
  onNarrowTextChange,
  onClear,
  datasets,
  pipelineConfigs,
}: RunsFilterBarProps) {
  const hasServerFilters =
    values.status !== '' ||
    values.evaluatorType !== '' ||
    values.datasetId !== '' ||
    values.pipelineConfigId !== ''
  const hasNarrow = narrowText.trim() !== ''
  const showClear = hasServerFilters || hasNarrow

  return (
    <fieldset className="cl-runs-filter-bar" data-testid="runs-filter-bar">
      <legend className="cl-runs-filter-legend">Search &amp; filter</legend>
      <p className="cl-runs-filter-hint cl-muted">
        Server filters refetch the list. <strong>Narrow visible rows</strong> applies only to the{' '}
        <em>currently loaded</em> page (run ID, status, query text, evaluator, dataset/pipeline ids, pipeline name).
      </p>
      <div className="cl-runs-filter-grid">
        <div className="cl-field cl-runs-filter-field">
          <label htmlFor="runs-filter-status">Status</label>
          <select
            id="runs-filter-status"
            data-testid="runs-filter-status"
            value={values.status}
            onChange={(e) => onChange({ status: e.target.value })}
          >
            <option value="">Any status</option>
            {RUN_FILTER_STATUS_VALUES.map((s) => (
              <option key={s} value={s}>
                {s.replace(/_/g, ' ')}
              </option>
            ))}
          </select>
        </div>
        <div className="cl-field cl-runs-filter-field">
          <label htmlFor="runs-filter-evaluator">Evaluator</label>
          <select
            id="runs-filter-evaluator"
            data-testid="runs-filter-evaluator"
            value={values.evaluatorType}
            onChange={(e) =>
              onChange({
                evaluatorType: e.target.value === '' ? '' : (e.target.value as 'heuristic' | 'llm'),
              })
            }
          >
            <option value="">Any</option>
            <option value="heuristic">Heuristic</option>
            <option value="llm">LLM</option>
          </select>
        </div>
        <div className="cl-field cl-runs-filter-field">
          <label htmlFor="runs-filter-dataset">Dataset</label>
          <select
            id="runs-filter-dataset"
            data-testid="runs-filter-dataset"
            value={values.datasetId === '' ? '' : String(values.datasetId)}
            onChange={(e) => {
              const v = e.target.value
              onChange({ datasetId: v === '' ? '' : Number(v) })
            }}
          >
            <option value="">Any dataset</option>
            {datasets.map((d) => (
              <option key={d.id} value={d.id}>
                {d.name} (#{d.id})
              </option>
            ))}
          </select>
        </div>
        <div className="cl-field cl-runs-filter-field">
          <label htmlFor="runs-filter-pipeline">Pipeline config</label>
          <select
            id="runs-filter-pipeline"
            data-testid="runs-filter-pipeline"
            value={values.pipelineConfigId === '' ? '' : String(values.pipelineConfigId)}
            onChange={(e) => {
              const v = e.target.value
              onChange({ pipelineConfigId: v === '' ? '' : Number(v) })
            }}
          >
            <option value="">Any config</option>
            {pipelineConfigs.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name} (#{c.id})
              </option>
            ))}
          </select>
        </div>
        <div className="cl-field cl-runs-filter-field cl-runs-filter-narrow">
          <label htmlFor="runs-filter-narrow">Narrow visible rows</label>
          <input
            id="runs-filter-narrow"
            data-testid="runs-filter-narrow"
            type="search"
            autoComplete="off"
            placeholder="e.g. run id, query snippet, heuristic…"
            value={narrowText}
            onChange={(e) => onNarrowTextChange(e.target.value)}
          />
        </div>
        <div className="cl-runs-filter-actions">
          <button
            type="button"
            className="cl-btn cl-btn-secondary"
            data-testid="runs-filter-clear"
            disabled={!showClear}
            onClick={onClear}
          >
            Clear filters
          </button>
        </div>
      </div>
    </fieldset>
  )
}
