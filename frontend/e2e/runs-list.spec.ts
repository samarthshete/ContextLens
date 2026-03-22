import { expect, test, type Page } from '@playwright/test'
import { installApiMetaRoute } from './fixtures'

const RUN_ROW: Record<string, unknown> = {
  status: 'completed',
  created_at: '2026-01-01T00:00:00Z',
  dataset_id: 1,
  query_case_id: 1,
  pipeline_config_id: 2,
  retrieval_latency_ms: null,
  generation_latency_ms: null,
  evaluation_latency_ms: null,
  total_latency_ms: null,
  evaluator_type: 'heuristic',
  has_evaluation: true,
}

async function mockRunsListApi(page: Page) {
  await installApiMetaRoute(page)
  await page.route('**/api/v1/datasets', (route) =>
    route.fulfill({
      json: [{ id: 1, name: 'DS', description: null, created_at: '2026-01-01T00:00:00Z' }],
      contentType: 'application/json',
    }),
  )
  await page.route('**/api/v1/pipeline-configs', (route) =>
    route.fulfill({
      json: [
        {
          id: 2,
          name: 'PC',
          embedding_model: 'm',
          chunk_strategy: 'fixed',
          chunk_size: 256,
          chunk_overlap: 0,
          top_k: 5,
          created_at: '2026-01-01T00:00:00Z',
        },
      ],
      contentType: 'application/json',
    }),
  )
  await page.route('**/api/v1/documents', (route) =>
    route.fulfill({ json: [], contentType: 'application/json' }),
  )
  await page.route('**/api/v1/query-cases*', (route) =>
    route.fulfill({ json: [], contentType: 'application/json' }),
  )

  await page.route('**/api/v1/runs**', async (route) => {
    const url = route.request().url()
    const completedOnly = url.includes('status=completed')
    const items = completedOnly
      ? [{ ...RUN_ROW, run_id: 5, query_text: 'only completed' }]
      : [
          { ...RUN_ROW, run_id: 5, query_text: 'only completed' },
          { ...RUN_ROW, run_id: 6, query_text: 'second run' },
        ]
    await route.fulfill({
      json: { items, total: items.length, limit: 25, offset: 0 },
      contentType: 'application/json',
    })
  })
}

test('runs list shows filter bar and status filter refetches', async ({ page }) => {
  await mockRunsListApi(page)
  await page.goto('/runs')
  await expect(page.getByTestId('runs-filter-bar')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Open' })).toHaveCount(2)
  await page.getByTestId('runs-filter-status').selectOption('completed')
  await expect(page.getByRole('button', { name: 'Open' })).toHaveCount(1)
})
