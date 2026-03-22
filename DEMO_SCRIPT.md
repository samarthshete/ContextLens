# ContextLens — Demo Walkthrough

**Length:** 2–3 minutes
**Audience:** Recruiters, hiring managers, technical interviewers
**Goal:** Show ContextLens as a serious AI infrastructure project, not a PDF chatbot.

---

## Opening (15 seconds)

"ContextLens is a RAG evaluation and debugging platform. When a retrieval-augmented generation system gives a wrong answer, ContextLens tells you exactly where the pipeline broke — retrieval, context, or generation — and gives you the data to fix it."

---

## Part 1 — Run a Benchmark (30 seconds)

1. Open the app at `localhost:5173` → land on the **Run** tab
2. Show the workflow: dataset, query case, pipeline config selectors are pre-populated from the registry
3. Point out the **document upload** panel — "You can upload PDFs, TXT, or Markdown directly from the UI"
4. Click **Run benchmark** with heuristic mode → instant result
5. "Heuristic mode evaluates retrieval quality without an LLM call. Full mode adds generation and an LLM judge, running through a durable Redis job queue."

---

## Part 2 — Inspect a Run Trace (45 seconds)

1. Navigate to **Recent Runs** → show the filterable list (status, evaluator type, dataset)
2. Click into a completed run → **Run Detail** page
3. Walk through top-to-bottom:
   - **Phase Timeline** — "Retrieval took 120ms, generation 3.1 seconds, evaluation 800ms. Generation dominated this run at 75% of total time."
   - **Diagnosis Summary** — "The system identified this as RETRIEVAL_PARTIAL — some relevant chunks were found but the top result had a weak score."
   - **Retrieval Hits** — "Each chunk shows its source document, relevance score, and rank. Source labels give immediate provenance."
   - **Context Quality** — "The system checks for thin chunks, prefix overlap between consecutive chunks, and context concentration in a single document."
   - **Generation & Judge** — "Faithfulness 0.85, completeness 0.6. The judge flagged incomplete coverage."

---

## Part 3 — Compare Runs (30 seconds)

1. In the Run Diff panel, enter a second run ID → click **Load comparison**
2. "Side-by-side, I can see Run B improved retrieval hit count from 3 to 5, top score went from 0.72 to 0.88, and failure type changed from RETRIEVAL_PARTIAL to NO_FAILURE."
3. "Every metric shows a verdict — improved, worse, or same — so you can see the impact of a config change at a glance."

---

## Part 4 — Dashboard (30 seconds)

1. Navigate to **Dashboard**
2. "The dashboard shows operational health across all runs."
3. Point to each panel:
   - **Trends** — "Daily run counts over 90 days, stacked by status"
   - **Latency** — "Median, p95, and max for each pipeline phase"
   - **Failures** — "Breakdown by failure type with per-config drill-down"
   - **Config Insights** — "Which configs have the best scores, lowest cost, and which ones need attention"

---

## Part 5 — Testing & Engineering Quality (15 seconds)

"The project has 345 automated tests: 141 backend pytest tests, 190 frontend Vitest tests, and 14 Playwright E2E tests. Backend tests run fully offline using deterministic fake embeddings. E2E tests use API mocking — no backend required."

---

## Closing (15 seconds)

"ContextLens is not a chatbot. It's an evaluation platform built with production patterns — trace storage, failure taxonomy, experiment tracking, durable job queues, and observability dashboards. The kind of tooling that makes RAG systems actually debuggable."

---

## Screenshot Sequence (for recording or slides)

1. **Run tab** — workflow form with dataset/query/config selectors + document upload
2. **Run detail** — phase timeline + diagnosis summary (showing a specific failure type)
3. **Retrieval hits** — source labels and scores visible
4. **Run diff** — comparison table with colored verdicts
5. **Dashboard** — all four panels visible (trends, latency, failures, config insights)
6. **Queue browser** — showing pending/running/completed runs with status column
7. **Terminal** — test output showing all 345 tests passing
