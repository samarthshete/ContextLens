import { test, expect, type Page } from '@playwright/test'
import { HEURISTIC_RUN, FULL_RUN, PARTIAL_RUN, installApiMetaRoute } from './fixtures'

/**
 * Mock all API routes so tests run without a backend.
 * Run-detail view primarily calls GET /api/v1/runs/{id}.
 * The workspace also loads registry on init.
 */
async function mockApi(page: Page) {
  await installApiMetaRoute(page)
  // Registry endpoints — return empty lists (safe)
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
  // Runs list
  await page.route('**/api/v1/runs?*', (route) =>
    route.fulfill({ json: { items: [], total: 0 }, contentType: 'application/json' }),
  )

  // Run detail — dispatch by run_id from URL
  await page.route('**/api/v1/runs/1', (route) =>
    route.fulfill({ json: HEURISTIC_RUN, contentType: 'application/json' }),
  )
  await page.route('**/api/v1/runs/2', (route) =>
    route.fulfill({ json: FULL_RUN, contentType: 'application/json' }),
  )
  await page.route('**/api/v1/runs/3', (route) =>
    route.fulfill({ json: PARTIAL_RUN, contentType: 'application/json' }),
  )
  await page.route('**/api/v1/runs/999', (route) =>
    route.fulfill({ status: 404, json: { detail: 'Run not found' }, contentType: 'application/json' }),
  )

  // Queue status — heuristic runs don't need Redis
  await page.route('**/api/v1/runs/*/queue-status', (route) =>
    route.fulfill({
      json: {
        run_id: 1,
        pipeline: 'heuristic',
        run_status: 'completed',
        lock_exists: false,
        job_id: null,
        rq_job_status: null,
        requeue_eligible: false,
      },
      contentType: 'application/json',
    }),
  )
}

// ---------------------------------------------------------------------------
// 1. Page loads correctly for a heuristic run
// ---------------------------------------------------------------------------
test('heuristic run detail loads all main sections', async ({ page }) => {
  await mockApi(page)
  await page.goto('/runs/1')

  // Page title area
  await expect(page.locator('h2').first()).toBeVisible()

  // Diagnosis summary
  const summary = page.locator('[data-testid="run-diagnosis-summary"]')
  await expect(summary).toBeVisible()

  // Phase timeline
  const timeline = page.locator('[data-testid="phase-timeline"]')
  await expect(timeline).toBeVisible()

  // Retrieval diagnosis
  await expect(page.locator('[data-testid="retrieval-diagnosis"]')).toBeVisible()

  // Context quality
  await expect(page.locator('[data-testid="context-quality"]')).toBeVisible()

  // Retrieval hits section
  await expect(page.locator('[data-testid="retrieval-hits-section"]')).toBeVisible()

  // Generation & judge insights
  await expect(page.locator('[data-testid="generation-judge-insights"]')).toBeVisible()

  // Run diff panel
  await expect(page.locator('[data-testid="run-diff-panel"]')).toBeVisible()
})

// ---------------------------------------------------------------------------
// 2. Phase timeline renders phase rows
// ---------------------------------------------------------------------------
test('phase timeline shows retrieval and evaluation rows', async ({ page }) => {
  await mockApi(page)
  await page.goto('/runs/1')

  await expect(page.locator('[data-testid="timeline-retrieval"]')).toBeVisible()
  await expect(page.locator('[data-testid="timeline-evaluation"]')).toBeVisible()
  await expect(page.locator('[data-testid="timeline-total"]')).toBeVisible()

  // Generation should show "—" for heuristic run
  const genRow = page.locator('[data-testid="timeline-generation"]')
  await expect(genRow).toBeVisible()
  await expect(genRow).toContainText('—')
})

// ---------------------------------------------------------------------------
// 3. Full run shows all timeline phases with generation
// ---------------------------------------------------------------------------
test('full run timeline shows generation dominant', async ({ page }) => {
  await mockApi(page)
  await page.goto('/runs/2')

  const genRow = page.locator('[data-testid="timeline-generation"]')
  await expect(genRow).toBeVisible()
  // Generation is dominant (3100ms of 4058ms)
  await expect(genRow).toHaveClass(/cl-timeline-dominant/)
})

// ---------------------------------------------------------------------------
// 4. Source labels appear on retrieval hits
// ---------------------------------------------------------------------------
test('retrieval hits show source labels', async ({ page }) => {
  await mockApi(page)
  await page.goto('/runs/1')

  // Hit #1 should have a source label
  const hit1 = page.locator('[data-testid="retrieval-hit-1"]')
  await expect(hit1).toBeVisible()
  await expect(hit1).toContainText('Source')
  await expect(hit1).toContainText('Document #1')

  // Hit #3 from a different document
  const hit3 = page.locator('[data-testid="retrieval-hit-3"]')
  await expect(hit3).toBeVisible()
  await expect(hit3).toContainText('Document #2')
})

// ---------------------------------------------------------------------------
// 5. Evaluation score grid visible for full run
// ---------------------------------------------------------------------------
test('full run shows evaluation score grid', async ({ page }) => {
  await mockApi(page)
  await page.goto('/runs/2')

  const grid = page.locator('[data-testid="evaluation-score-grid"]')
  await expect(grid).toBeVisible()
  await expect(grid).toContainText('Faithfulness')
  await expect(grid).toContainText('Completeness')
})

// ---------------------------------------------------------------------------
// 6. RunDiffPanel: load comparison run
// ---------------------------------------------------------------------------
test('diff panel loads and shows comparison table', async ({ page }) => {
  await mockApi(page)
  await page.goto('/runs/1')

  const diffPanel = page.locator('[data-testid="run-diff-panel"]')
  await expect(diffPanel).toBeVisible()

  // Before loading — empty state
  await expect(diffPanel).toContainText('Enter a run ID')

  // Type a comparison run ID and click Load
  await page.fill('#run-diff-other-id', '2')
  await page.click('[data-testid="run-diff-panel"] button:has-text("Load comparison")')

  // Wait for the diff summary to appear
  const diffSummary = page.locator('[data-testid="run-diff-summary"]')
  await expect(diffSummary).toBeVisible({ timeout: 5000 })

  // Should show the comparison table with metric rows
  await expect(diffPanel).toContainText('Run A')
  await expect(diffPanel).toContainText('Run B')
  await expect(diffPanel).toContainText('Retrieval hit count')
})

// ---------------------------------------------------------------------------
// 7. RunDiffPanel: invalid ID shows error
// ---------------------------------------------------------------------------
test('diff panel shows error for invalid ID', async ({ page }) => {
  await mockApi(page)
  await page.goto('/runs/1')

  await page.fill('#run-diff-other-id', 'abc')
  await page.click('[data-testid="run-diff-panel"] button:has-text("Load comparison")')

  const error = page.locator('[data-testid="run-diff-panel"] [role="alert"]')
  await expect(error).toBeVisible()
  await expect(error).toContainText('positive integer')
})

// ---------------------------------------------------------------------------
// 8. RunDiffPanel: same ID as current run shows error
// ---------------------------------------------------------------------------
test('diff panel rejects same run ID', async ({ page }) => {
  await mockApi(page)
  await page.goto('/runs/1')

  await page.fill('#run-diff-other-id', '1')
  await page.click('[data-testid="run-diff-panel"] button:has-text("Load comparison")')

  const error = page.locator('[data-testid="run-diff-panel"] [role="alert"]')
  await expect(error).toBeVisible()
  await expect(error).toContainText('different run ID')
})

// ---------------------------------------------------------------------------
// 9. Partial / missing data safety — running run with no eval/gen
// ---------------------------------------------------------------------------
test('partial run renders without crash', async ({ page }) => {
  await mockApi(page)
  await page.goto('/runs/3')

  // Page should render even with no evaluation/generation
  await expect(page.locator('[data-testid="run-diagnosis-summary"]')).toBeVisible()

  // No retrieval hits — should say so
  const hitsSection = page.locator('[data-testid="retrieval-hits-section"]')
  await expect(hitsSection).toBeVisible()
  await expect(hitsSection).toContainText('No chunks retrieved')

  // Generation section should indicate no generation
  const genPanel = page.locator('[data-testid="generation-judge-insights"]')
  await expect(genPanel).toBeVisible()
})

// ---------------------------------------------------------------------------
// 10. 404 run — error handling
// ---------------------------------------------------------------------------
test('nonexistent run shows error', async ({ page }) => {
  await mockApi(page)
  await page.goto('/runs/999')

  // Should show an error alert rather than crashing
  const alert = page.locator('[role="alert"]')
  await expect(alert).toBeVisible({ timeout: 5000 })
})

// ---------------------------------------------------------------------------
// 11. Non-numeric run ID — handled by router
// ---------------------------------------------------------------------------
test('invalid non-numeric run ID shows error', async ({ page }) => {
  await mockApi(page)
  await page.goto('/runs/abc')

  // Router should show inline error for non-numeric ID
  await expect(page.getByText(/not a valid/i).or(page.getByText(/invalid/i))).toBeVisible()
})
