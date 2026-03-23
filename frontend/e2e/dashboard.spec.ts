import { expect, test, type Page } from '@playwright/test'
import { installApiMetaRoute } from './fixtures'

async function mockDashboardApi(page: Page) {
  await installApiMetaRoute(page)
  await page.route('**/api/v1/datasets', (route) =>
    route.fulfill({ json: [], contentType: 'application/json' }),
  )
  await page.route('**/api/v1/pipeline-configs', (route) =>
    route.fulfill({ json: [], contentType: 'application/json' }),
  )
  await page.route('**/api/v1/documents', (route) =>
    route.fulfill({ json: [], contentType: 'application/json' }),
  )
  await page.route('**/api/v1/runs/dashboard-summary', (route) =>
    route.fulfill({
      json: {
        total_runs: 2,
        scale: {
          benchmark_datasets: 1,
          total_queries: 4,
          total_traced_runs: 2,
          configs_tested: 2,
          documents_processed: 3,
          chunks_indexed: 12,
        },
        status_counts: { completed: 2, failed: 0, in_progress: 0 },
        evaluator_counts: { heuristic_runs: 2, llm_runs: 0, runs_without_evaluation: 0 },
        latency: {
          avg_retrieval_latency_ms: 10,
          retrieval_latency_p50_ms: 10,
          retrieval_latency_p95_ms: 12,
          avg_generation_latency_ms: null,
          avg_evaluation_latency_ms: 5,
          avg_total_latency_ms: 20,
          end_to_end_run_latency_avg_sec: 0.02,
          end_to_end_run_latency_p95_sec: 0.025,
        },
        cost: {
          total_cost_usd: null,
          avg_cost_usd: null,
          evaluation_rows_with_cost: 0,
          evaluation_rows_cost_not_available: 2,
        },
        failure_type_counts: {},
        recent_runs: [],
      },
      contentType: 'application/json',
    }),
  )
  await page.route('**/api/v1/runs/dashboard-analytics', (route) =>
    route.fulfill({
      json: {
        time_series: [
          {
            date: '2026-03-20',
            runs: 5,
            completed: 4,
            failed: 1,
            avg_total_latency_ms: 100,
            avg_cost_usd: null,
            failure_count: 1,
          },
        ],
        latency_distribution: {
          retrieval: { count: 2, min_ms: 1, max_ms: 50, avg_ms: 20, median_ms: 18, p95_ms: 45 },
          generation: { count: 0, min_ms: null, max_ms: null, avg_ms: null, median_ms: null, p95_ms: null },
          evaluation: { count: 2, min_ms: 2, max_ms: 30, avg_ms: 10, median_ms: 9, p95_ms: 28 },
          total: { count: 2, min_ms: 20, max_ms: 200, avg_ms: 100, median_ms: 95, p95_ms: 180 },
        },
        end_to_end_run_latency_avg_sec: 0.1,
        end_to_end_run_latency_p95_sec: 0.18,
        failure_analysis: {
          overall_counts: { NO_FAILURE: 1, UNKNOWN: 1 },
          overall_percentages: { NO_FAILURE: 50, UNKNOWN: 50 },
          by_config: [],
          recent_failed_runs: [],
        },
        config_insights: { heuristic: [], llm: [] },
      },
      contentType: 'application/json',
    }),
  )
}

test('dashboard shows observability heading and trend chart', async ({ page }) => {
  await mockDashboardApi(page)
  await page.goto('/dashboard')
  await expect(page.getByRole('heading', { name: 'Observability', level: 2 })).toBeVisible()
  await expect(page.getByTestId('dashboard-system-scale')).toBeVisible()
  await expect(page.getByTestId('dashboard-trends-chart')).toBeVisible()
  await expect(page.getByTestId('latency-distribution')).toBeVisible()
})
