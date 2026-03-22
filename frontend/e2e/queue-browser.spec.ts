import { expect, test, type Page } from '@playwright/test'
import { installApiMetaRoute } from './fixtures'

const RUN_ROW = {
  status: 'running',
  created_at: '2026-01-01T00:00:00Z',
  dataset_id: 1,
  query_case_id: 1,
  pipeline_config_id: 1,
  query_text: 'q',
  retrieval_latency_ms: null,
  generation_latency_ms: null,
  evaluation_latency_ms: null,
  total_latency_ms: null,
  evaluator_type: 'none',
  has_evaluation: false,
}

async function mockQueueBrowserApi(page: Page) {
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
  await page.route('**/api/v1/query-cases*', (route) =>
    route.fulfill({ json: [], contentType: 'application/json' }),
  )

  await page.route('**/api/v1/runs?*', async (route) => {
    const u = new URL(route.request().url())
    const st = u.searchParams.get('status')
    if (st === 'running') {
      await route.fulfill({
        json: {
          items: [{ ...RUN_ROW, run_id: 77 }],
          total: 1,
          limit: 20,
          offset: 0,
        },
        contentType: 'application/json',
      })
      return
    }
    await route.fulfill({
      json: { items: [], total: 0, limit: 20, offset: 0 },
      contentType: 'application/json',
    })
  })

  await page.route('**/api/v1/runs/77/queue-status', (route) =>
    route.fulfill({
      json: {
        run_id: 77,
        run_status: 'running',
        pipeline: 'heuristic',
        job_id: null,
        rq_job_status: null,
        lock_present: false,
        requeue_eligible: false,
        detail: null,
      },
      contentType: 'application/json',
    }),
  )
}

test('queue browser loads row and queue-status refresh', async ({ page }) => {
  await mockQueueBrowserApi(page)
  await page.goto('/queue')
  await expect(page.getByTestId('queue-browser')).toBeVisible()
  await expect(page.getByTestId('queue-browser-row-77')).toBeVisible()
  await page.getByTestId('queue-browser-refresh-qs-77').click()
  await expect(page.getByTestId('queue-browser-heuristic-77')).toBeVisible()
})
