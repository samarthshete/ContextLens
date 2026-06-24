import type { Dataset, PipelineConfig, RunListItem } from '../api/types'
import { DataTable, EmptyState, SectionHeader, StatusBadge } from './ui'
import { RunsFilterBar } from './RunsFilterBar'
import type { RunsListServerFilters } from './runsListQuery'

function formatWhen(iso: string): string {
  try {
    return new Date(iso).toLocaleString()
  } catch {
    return iso
  }
}

function pipelineLabel(id: number, configs: PipelineConfig[]): string {
  const p = configs.find((c) => c.id === id)
  return p ? `${p.name} (#${id})` : `config #${id}`
}

export function RunsListView({
  runs,
  runsVisible,
  runsTotal,
  runsHasMore,
  runsLoading,
  runsFilters,
  runsNarrowText,
  datasets,
  pipelineConfigs,
  onFiltersChange,
  onNarrowTextChange,
  onClearFilters,
  onRefresh,
  onLoadMore,
  onOpenRun,
}: {
  runs: RunListItem[]
  runsVisible: RunListItem[]
  runsTotal: number
  runsHasMore: boolean
  runsLoading: boolean
  runsFilters: RunsListServerFilters
  runsNarrowText: string
  datasets: Dataset[]
  pipelineConfigs: PipelineConfig[]
  onFiltersChange: (partial: Partial<RunsListServerFilters>) => void
  onNarrowTextChange: (value: string) => void
  onClearFilters: () => void
  onRefresh: () => void
  onLoadMore: () => void
  onOpenRun: (runId: number) => void
}) {
  return (
    <section className="cl-card cl-runs-view">
      <SectionHeader
        eyebrow="Trace index"
        title="Recent runs"
        description="Open a run to inspect retrieval evidence, generated answer, LLM judge scores, failure labels, and latency."
        actions={
          <button type="button" className="cl-btn cl-btn-secondary cl-btn-sm" disabled={runsLoading} onClick={onRefresh}>
            {runsLoading ? 'Loading...' : 'Refresh'}
          </button>
        }
      />
      <RunsFilterBar
        values={runsFilters}
        narrowText={runsNarrowText}
        onChange={onFiltersChange}
        onNarrowTextChange={onNarrowTextChange}
        onClear={onClearFilters}
        datasets={datasets}
        pipelineConfigs={pipelineConfigs}
      />
      <p className="cl-muted">
        Showing {runsVisible.length} of {runs.length} on this page · {runsTotal} total match current filters
        {runsNarrowText.trim() ? ' (narrow filter active on loaded rows)' : ''} · newest first
      </p>

      {runsLoading && !runs.length ? (
        <p className="cl-loading">Loading runs...</p>
      ) : !runs.length ? (
        <EmptyState title="No runs yet" detail="Create one from Run benchmark to populate trace inspection." />
      ) : runsVisible.length === 0 ? (
        <div data-testid="runs-narrow-empty">
          <EmptyState title="No matching runs on this page" detail="Clear the narrow filter or load more rows." />
        </div>
      ) : (
        <DataTable className="cl-runs-table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Created</th>
              <th>Status</th>
              <th>Pipeline</th>
              <th>Query</th>
              <th>Evaluator</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {runsVisible.map((r) => (
              <tr key={r.run_id}>
                <td>{r.run_id}</td>
                <td>{formatWhen(r.created_at)}</td>
                <td>
                  <StatusBadge status={r.status} />
                </td>
                <td>{pipelineLabel(r.pipeline_config_id, pipelineConfigs)}</td>
                <td>
                  {r.query_text.slice(0, 48)}
                  {r.query_text.length > 48 ? '...' : ''}
                </td>
                <td>{r.evaluator_type}</td>
                <td>
                  <button type="button" className="cl-btn cl-btn-secondary cl-btn-sm" onClick={() => onOpenRun(r.run_id)}>
                    Open
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </DataTable>
      )}

      {runsHasMore ? (
        <div className="cl-actions">
          <button type="button" className="cl-btn cl-btn-secondary" disabled={runsLoading} onClick={onLoadMore}>
            {runsLoading ? 'Loading...' : 'Load more'}
          </button>
        </div>
      ) : null}
    </section>
  )
}
