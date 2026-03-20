# ContextLens

**ContextLens** is a RAG evaluation and debugging platform for developers building document-grounded AI systems. It helps answer one question fast:

> **My RAG pipeline gave a bad answer. Where exactly did it fail?**

Instead of treating retrieval-augmented generation as a black box, ContextLens captures the full trace from query to answer and evaluates each stage: retrieval quality, context coverage, answer faithfulness, completeness, and failure type.

---

## Why this project exists

Most RAG demos stop at “upload a PDF and ask a question.” That is not enough for real engineering work.

When a RAG system fails, teams usually do not know whether the problem came from:

- bad chunking
- weak retrieval
- wrong context selection
- context truncation
- unsupported generation
- incomplete answers

ContextLens is built to make those failures visible, measurable, and comparable.

---

## What ContextLens does

- Uploads and parses documents
- Splits documents into chunks using configurable strategies
- Stores embeddings and retrieves relevant chunks with pgvector
- Runs question-answering over retrieved context
- Captures the full run trace for every query
- Evaluates retrieval and answer quality with hybrid scoring
- Classifies failure modes like retrieval miss, context truncation, and unsupported answers
- Compares pipeline configurations across datasets and benchmarks

---

## Core features

### 1. RAG trace capture
Every run stores:
- query
- selected pipeline config
- retrieved chunks
- final context sent to the model
- generated answer
- latencies and token usage

### 2. Evaluation engine
Each run is scored on:
- retrieval relevance
- context coverage
- faithfulness
- completeness
- correctness (when reference answers exist)

### 3. Failure classification
ContextLens identifies common RAG breakdowns such as:
- retrieval miss
- retrieval partial
- chunk fragmentation
- context truncation
- answer unsupported
- answer incomplete
- mixed failure

### 4. Benchmarking and comparison
The platform supports dataset-driven experiments so developers can compare:
- chunking strategies
- top-k retrieval settings
- prompt templates
- embedding models
- pipeline configurations

### 5. Developer-facing UI
A React (Vite + TypeScript) app includes a **benchmark flow**: pick dataset → query case → pipeline config → optional document (**upload PDF/TXT/Markdown via `POST /api/v1/documents` in the Run tab**, or pick an existing doc) → run `POST /api/v1/runs` (**heuristic** finishes inline; **full** returns **202** and the UI polls run status), then open **run list**, **run detail**, and **config comparison**. (Broader document/chunk inspection UIs can extend the same API surface.)

---

## Tech stack

### Backend
- FastAPI
- SQLAlchemy (async)
- Alembic
- PostgreSQL 16
- pgvector

### Frontend
- React
- Vite
- TypeScript
- Component CSS (shared tokens in `index.css`)

### AI/ML
- sentence-transformers (`all-MiniLM-L6-v2`) for embeddings
- Claude Sonnet for answer generation and evaluation

---

## Repository structure

```text
contextlens/
├── README.md
├── LICENSE
├── .gitignore
├── .env.example
├── PROJECT.md
├── CURRENT_STATE.md
├── TASK.md
├── DECISIONS.md
├── CONTRIBUTING.md
├── ROADMAP.md
├── DEMO_SCRIPT.md
├── docs/
│   ├── architecture.md
│   ├── api.md
│   ├── metrics.md
│   └── screenshots.md
├── backend/
├── frontend/
├── datasets/
└── scripts/
```

---

## Current status

ContextLens is being built in phases.

### Done
- project architecture frozen
- data model defined
- API surface defined
- phase plan created
- GitHub documentation pack created

### In progress
- Phase 1: foundation validation
- backend scaffold audit
- Docker + database validation

### Next
- Phase 2: document ingestion and chunking

See `CURRENT_STATE.md` and `TASK.md` for the live build state.

---

## Planned architecture

```text
[React Dashboard]
       ↓
[FastAPI API Layer]
       ↓
[Service Layer]
       ↓
[PostgreSQL + pgvector]
       ↓
[Embedding / LLM Services]
```

### Query flow
1. User uploads a document
2. Backend parses text and creates chunks
3. Chunks are embedded and stored
4. User submits a query
5. Retriever returns top-k chunks
6. Final context is assembled
7. LLM generates answer
8. Full trace is stored
9. Evaluation runs
10. Failure type is assigned

---

## Example failure taxonomy

- `NO_FAILURE`
- `RETRIEVAL_MISS`
- `RETRIEVAL_PARTIAL`
- `CHUNK_FRAGMENTATION`
- `CONTEXT_TRUNCATION`
- `ANSWER_UNSUPPORTED`
- `ANSWER_INCOMPLETE`
- `MIXED_FAILURE`
- `UNKNOWN`

---

## Metrics this project will track

### ContextLens
- benchmark datasets
- total queries
- total traced runs
- pipeline configs tested
- retrieval latency
- evaluation latency
- classification agreement
- debugging time before/after
- evaluation cost per run
- hybrid evaluation cost reduction

See `docs/METRICS_INSTRUMENTATION.md` and **`docs/BENCHMARK_WORKFLOW.md`** (seed → run benchmarks → regenerate `PROJECT_METRICS.md`).

---

## Local development

### 1. Clone
```bash
git clone <your-repo-url>
cd contextlens
```

### 2. Configure environment
```bash
cp .env.example .env
```

Set your DB and Anthropic key.

### 3. Start infrastructure
```bash
docker compose up db -d
```

For **`eval_mode=full`** from the benchmark UI or `POST /api/v1/runs`, also run **Redis** and an **RQ worker** (see **`backend/README.md`**):

```bash
docker compose up redis -d
cd backend && source .venv/bin/activate  # after venv exists
export REDIS_URL=redis://localhost:6379/0
rq worker contextlens_full_run --url "$REDIS_URL"
```

Or use **`docker compose up`** to start **db**, **redis**, **backend**, and **worker** together.

### 4. Backend
```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --reload
```

### Optional: benchmark rows → generated metrics
```bash
cd backend
python scripts/seed_benchmark.py
python scripts/run_benchmark.py
python scripts/generate_contextlens_metrics.py --format markdown
```
Details: `docs/BENCHMARK_WORKFLOW.md`, `docs/FULL_RAG_EXAMPLE.md` (full RAG + `CLAUDE_API_KEY`).

### 5. Frontend (benchmark UI)
Vite proxies `/api` → **`BACKEND_PROXY_TARGET`** (default **`http://127.0.0.1:8002`** — matches `uvicorn --port 8002`). For Compose’s API on **:8000**, set `BACKEND_PROXY_TARGET=http://127.0.0.1:8000` in `frontend/.env.development.local` (see `frontend/.env.example`).
```bash
cd frontend
npm install
npm run dev
# open http://localhost:5173 — use “Run benchmark” after seeding data (see BENCHMARK_WORKFLOW.md)
```
Optional: `VITE_API_BASE=http://127.0.0.1:8002/api/v1` if you disable the proxy (ensure CORS).

**Full mode from UI/API:** Redis + **`rq worker contextlens_full_run`** — operational checklist, restart semantics, and **`check_redis_for_rq.py`** in **`docs/DEV_FULL_RUN_QUEUE.md`** (also `backend/README.md`, `docker-compose.yml` **`worker`**).

**Automated tests (current):** **95** `pytest` tests in `backend/tests/`; **14** Vitest tests in `frontend/` (`npm run test`).

---

## Demo

See `DEMO_SCRIPT.md` for the exact 2-minute walkthrough and voiceover sequence.

A simple demo flow:
1. Upload a policy PDF
2. Ask a question with a known edge case
3. Show retrieved chunks
4. Show generated answer
5. Show evaluation scores
6. Show failure classification
7. Compare two configs and explain the difference

---

## Resume positioning

**ContextLens** is positioned as an AI infrastructure / developer tooling project, not a chatbot. It demonstrates:
- RAG system design
- backend engineering
- vector retrieval
- experiment tracking
- evaluation design
- failure analysis
- benchmark-driven iteration

Example resume bullet:

> Built **ContextLens**, a RAG evaluation and debugging platform that captures retrieval-to-generation traces, classifies common failure modes, and supports benchmarking across chunking, retrieval, and prompt configurations.

---

## Roadmap

See `ROADMAP.md` for the full phase-by-phase build plan.

---

## Contributing

This project is currently under active solo development. Suggestions, bug reports, and design feedback are welcome once the public roadmap is stabilized.

---

## License

MIT License. See `LICENSE`.
