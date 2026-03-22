# Local Verification Checklist

Run this checklist before pushing to GitHub. Every command should succeed.

---

## 1. Backend tests

```bash
cd /Users/samarthshete/Desktop/ContextLens/backend
pytest --tb=short -q
```

**Expected:** `141 passed` (exact count per `CURRENT_STATE.md`). All tests run offline — no model download, no API key, no running database needed (uses ASGI test client + in-memory fixtures).

---

## 2. Frontend unit/integration tests

```bash
cd /Users/samarthshete/Desktop/ContextLens/frontend
npm run test -- --run
```

**Expected:** `190 tests passed` (verified 2026-03-21). Uses Vitest with mocked API — no backend needed.

---

## 3. Frontend build and lint

```bash
cd /Users/samarthshete/Desktop/ContextLens/frontend
npm run build
npm run lint
```

**Expected:** Both exit 0 with no errors. Build output goes to `frontend/dist/`.

---

## 4. Playwright browser install

```bash
cd /Users/samarthshete/Desktop/ContextLens/frontend
npx playwright install chromium
```

**Expected:** Downloads Chromium binary to Playwright's local cache. Required once per machine. If already installed, this is a no-op.

---

## 5. Playwright E2E tests

```bash
cd /Users/samarthshete/Desktop/ContextLens/frontend
npx playwright test
```

**Expected:** `14 passed` across 4 spec files:
- `e2e/run-detail.spec.ts` — 11 tests
- `e2e/runs-list.spec.ts` — 1 test
- `e2e/queue-browser.spec.ts` — 1 test
- `e2e/dashboard.spec.ts` — 1 test

These run against `vite preview` (auto-started by Playwright config on port 4173). API calls are intercepted via `page.route()` with deterministic fixtures — **no backend required**.

> If `vite preview` fails to start, run `npm run build` first — preview serves from `dist/`.

---

## 6. Verify screenshot paths

```bash
ls /Users/samarthshete/Desktop/ContextLens/docs/images/
```

**Expected files** (after screenshots are captured per `docs/SCREENSHOT_CAPTURE_PLAN.md`):
- `run-workflow.png`
- `dashboard-overview.png`
- `run-diagnosis-hero.png`
- `retrieval-source-inspection.png`
- `run-diff.png`
- `runs-filters.png`
- `test-suite.png`

If screenshots are not yet captured, the directory should at minimum contain `.gitkeep`.

---

## 7. README sanity check

```bash
# Verify README references match actual files
grep -o 'docs/images/[a-z\-]*.png' /Users/samarthshete/Desktop/ContextLens/README.md | sort
ls /Users/samarthshete/Desktop/ContextLens/docs/images/*.png 2>/dev/null | xargs -I{} basename {} | sort
```

Both lists should match. Any mismatch means a broken image link on GitHub.

---

## 8. No junk files

```bash
cd /Users/samarthshete/Desktop/ContextLens
git status
```

**Check for:**
- No `.env` files staged (only `.env.example` should be committed)
- No `node_modules/`, `__pycache__/`, `.venv/`, `dist/` in the diff
- No large binary files accidentally staged
- `test.txt` in the root — check if this is intentional or leftover; remove if junk

---

## 9. Final git diff review

```bash
cd /Users/samarthshete/Desktop/ContextLens
git diff --stat
git diff --cached --stat
```

Review that only intended files appear. The README rewrite, screenshot plan, verification checklist, and docs/images directory should be the primary changes.
