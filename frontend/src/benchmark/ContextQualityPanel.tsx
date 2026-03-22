import type { RunDetail } from '../api/types'
import { computeContextQuality } from './runDiagnosis'

export function ContextQualityPanel({ runDetail }: { runDetail: RunDetail }) {
  const q = computeContextQuality(runDetail.retrieval_hits, runDetail.pipeline_config.top_k)

  return (
    <section className="cl-card cl-diagnosis-panel" data-testid="context-quality">
      <h3 className="cl-diagnosis-title">Context quality</h3>
      <p className="cl-muted">
        Chunk sizes and simple heuristics for <strong>thin</strong> context, <strong>sparse</strong>{' '}
        retrieval vs <code>top_k</code>, and <strong>repetition</strong>.
      </p>
      {q.chunkRows.length === 0 ? (
        <p className="cl-muted cl-empty-inline">No chunks to measure.</p>
      ) : (
        <div className="cl-table-wrap">
          <table className="cl-table cl-diagnosis-table">
            <thead>
              <tr>
                <th>Rank</th>
                <th>Chars</th>
              </tr>
            </thead>
            <tbody>
              {q.chunkRows.map((r) => (
                <tr key={r.rank}>
                  <td>{r.rank}</td>
                  <td>{r.lengthChars}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <dl className="cl-dash-dl cl-diagnosis-dl">
        <div className="cl-dash-dl-row">
          <dt>Chunks (count)</dt>
          <dd>{q.chunkRows.length}</dd>
        </div>
        <div className="cl-dash-dl-row">
          <dt>Total context chars</dt>
          <dd>{q.totalChars}</dd>
        </div>
        <div className="cl-dash-dl-row">
          <dt>Avg chars / chunk</dt>
          <dd>{q.avgChars != null ? Math.round(q.avgChars) : 'N/A'}</dd>
        </div>
        <div className="cl-dash-dl-row">
          <dt>Thin context?</dt>
          <dd>{q.thinContext ? 'Yes — unusually short snippets' : 'No'}</dd>
        </div>
        <div className="cl-dash-dl-row">
          <dt>Sparse vs top_k?</dt>
          <dd>
            {q.sparseContext
              ? `Yes — fewer hits than you might expect for top_k=${runDetail.pipeline_config.top_k}`
              : 'No'}
          </dd>
        </div>
      </dl>
      {q.repetitiveWarning ? (
        <p className="cl-diagnosis-warn" role="status">
          {q.repetitiveWarning}
        </p>
      ) : null}
      {q.notes.length > 0 ? (
        <ul className="cl-diagnosis-list">
          {q.notes.map((t, i) => (
            <li key={i}>{t}</li>
          ))}
        </ul>
      ) : null}
    </section>
  )
}
