import type { ReactNode } from 'react'
import type { View } from './BenchmarkWorkspace'

const navItems: Array<{ view: View; label: string; shortLabel: string }> = [
  { view: 'dashboard', label: 'Overview', shortLabel: 'Overview' },
  { view: 'runs', label: 'Runs', shortLabel: 'Runs' },
  { view: 'detail', label: 'Trace detail', shortLabel: 'Trace' },
  { view: 'compare', label: 'Compare', shortLabel: 'Compare' },
  { view: 'run', label: 'Run benchmark', shortLabel: 'Run' },
  { view: 'queue', label: 'Queue', shortLabel: 'Queue' },
]

export function AppShell({
  view,
  onNavigate,
  children,
}: {
  view: View
  onNavigate: (view: View) => void
  children: ReactNode
}) {
  return (
    <div className="cl-app">
      <header className="cl-product-shell">
        <div className="cl-product-topline">
          <div>
            <p className="cl-eyebrow">RAG evaluation platform</p>
            <h1>ContextLens</h1>
            <p className="cl-product-subtitle">
              Production-style evals for retrieval quality, generated answers, LLM-as-judge scoring, and trace-level
              failure diagnosis.
            </p>
          </div>
          <div className="cl-product-status" aria-label="System status">
            <span className="cl-live-dot" />
            API hardened · request IDs · CI verified
          </div>
        </div>

        <div className="cl-proof-strip" aria-label="Product proof metrics">
          <span>
            <strong>208</strong> traced runs
          </span>
          <span>
            <strong>52</strong> benchmark queries
          </span>
          <span>
            <strong>10</strong> failure categories
          </span>
          <span>
            <strong>LLM-as-judge</strong> scoring
          </span>
          <span>
            <strong>Trace-level</strong> diagnosis
          </span>
        </div>

        <nav className="cl-nav" aria-label="Main">
          {navItems.map((item) => (
            <button
              key={item.view}
              type="button"
              aria-label={item.label}
              data-active={view === item.view}
              onClick={() => onNavigate(item.view)}
            >
              <span className="cl-nav-full">{item.label}</span>
              <span className="cl-nav-short">{item.shortLabel}</span>
            </button>
          ))}
        </nav>
      </header>

      <main>{children}</main>
    </div>
  )
}
