/** Below this many distinct runs with an LLM-bucket evaluation, show a low-sample warning on the dashboard. */
export const DASHBOARD_LLM_EVIDENCE_MIN_RUNS = 10

/** Below this count, hide LLM cost, LLM comparison bucket, and LLM config-insights table (sparse warning only). */
export const DASHBOARD_LLM_SPARSE_GATE_RUNS = 3

/** Minimum total-phase samples before showing latency distribution charts. */
export const DASHBOARD_LATENCY_DIST_MIN_RUNS = 5

/** Below this sample count per phase, show a "Low sample — not reliable" badge. */
export const DASHBOARD_LATENCY_LOW_SAMPLE_THRESHOLD = 20

/** When P95 / P50 exceeds this ratio, show a "High variance (skewed distribution)" badge. */
export const DASHBOARD_LATENCY_HIGH_VARIANCE_RATIO = 10

/** Below this many traced runs per config in comparison, show reliability warning instead of full table. */
export const DASHBOARD_COMPARE_MIN_RUNS_FOR_TABLE = 10
