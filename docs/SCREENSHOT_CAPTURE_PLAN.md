# Screenshot Capture Plan

Capture these 7 screenshots in order. Each maps to a section in `README.md`.

All files go in `docs/images/`. The README already references these exact paths.

---

## Prerequisites before capturing

1. Backend running with seeded data (at least 6–8 benchmark runs, mixed heuristic + full if possible)
2. Frontend running via `npm run dev` at `http://localhost:5173`
3. Browser window at a clean width (~1280px) — no dev tools open
4. Light background (component CSS tokens are already clean)

---

## 1. `run-workflow.png` — Run Workflow Entry

**Route:** `/benchmark`

**What to show:**
- Dataset, query case, and pipeline config selectors populated from registry
- Document upload panel visible (collapsed or with a document already selected)
- Corpus scope block visible
- Run button visible

**Crop:** Just the main content area below the nav bar. Include the full workflow form.

---

## 2. `dashboard-overview.png` — Dashboard Overview

**Route:** `/dashboard`

**What to show:**
- All four panels visible in a single capture: trend chart, latency distribution, failure breakdown, config insights
- Seeded data so bars and tables are populated (not empty state)
- Summary stats at the top (total runs, completed, failed)

**Crop:** Full dashboard content area. Scroll if needed to get all four panels, or take a tall screenshot.

---

## 3. `run-diagnosis-hero.png` — Run Diagnosis (Hero Screenshot)

**Route:** `/runs/:runId` — pick a run that has a non-trivial failure type (e.g. `RETRIEVAL_PARTIAL` or `CHUNK_FRAGMENTATION`)

**What to show:**
- Phase timeline with proportional colored bars and dominant-phase highlight
- Diagnosis summary showing the identified failure type and supporting evidence lines
- Top of the retrieval hits section visible below

**This is the money shot.** It should communicate: "this tool tells you exactly what went wrong."

**Crop:** From the run header through the diagnosis summary. Cut before the raw JSON or deep details.

---

## 4. `retrieval-source-inspection.png` — Retrieval Source Inspection

**Route:** `/runs/:runId` — same or different run, scroll to retrieval hits

**What to show:**
- 3–5 retrieval hit rows visible
- Each showing: rank number, cosine similarity score, source document label ("Source: Document #N" or title), chunk text preview
- Source diversity note if visible (e.g. "All hits from one document")

**Crop:** Just the retrieval hits section. Clean cut above and below.

---

## 5. `run-diff.png` — Run Diff

**Route:** `/runs/:runId` — scroll to the Run Diff panel

**Setup:** Enter a second run ID (one that differs meaningfully — different config or different result) and click "Load comparison" before capturing.

**What to show:**
- Comparison table with Run A / Run B columns
- Colored verdict badges: green `improved`, red `worse`, neutral `same`
- Multiple metric rows visible (hits, top score, context size, failure type, eval scores)
- Summary lines at the bottom if visible

**Crop:** The diff panel from header through the comparison table.

---

## 6. `runs-filters.png` — Runs List with Filters

**Route:** `/runs`

**What to show:**
- Filter bar active with at least one filter selected (e.g. status = "completed")
- Several run rows visible with columns (run ID, status, query text, evaluator type)
- "Narrow visible rows" text input if visible

**Crop:** Filter bar + first several rows of the runs table.

---

## 7. `test-suite.png` — Test Suite Evidence

**Terminal capture, not browser.**

**Option A (side-by-side):** Two terminal panes showing:
- Left: `cd backend && pytest` output with "138 passed" summary line
- Right: `cd frontend && npm run test -- --run` output with "163 tests passed" summary

**Option B (stacked):** Single terminal with sequential output:
```bash
cd backend && pytest --tb=no -q
cd ../frontend && npm run test -- --run
npx playwright test
```

**What to show:**
- Final summary lines with pass counts (138 + 163 + 14)
- All green / all passing — no failures

**Crop:** Just the summary output. No need to show every individual test name.

---

## File checklist

After capture, verify all files exist:

```bash
ls -la docs/images/
# Expected:
#   run-workflow.png
#   dashboard-overview.png
#   run-diagnosis-hero.png
#   retrieval-source-inspection.png
#   run-diff.png
#   runs-filters.png
#   test-suite.png
```

All 7 paths are already referenced in `README.md`. Missing files will render as broken images on GitHub.
