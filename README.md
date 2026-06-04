# ContextLens

ContextLens is a RAG evaluation and debugging platform for understanding why retrieval-augmented generation runs succeed or fail.

Instead of stopping at document upload and question answering, ContextLens captures the trace around each run: query, pipeline config, retrieved chunks, generated answer, latency fields, evaluation result, failure type, and comparison data.

## Problem Solved

RAG systems can fail for different reasons that look similar from the outside:

- The retriever missed the relevant passage.
- The right context was split across chunks.
- Context was present but the answer was incomplete.
- The model generated content not supported by retrieved context.
- A full-mode run failed because of infrastructure or queue issues.

ContextLens turns those cases into inspectable traces, evaluation rows, dashboard summaries, and run comparisons.

## Key Features

- Document upload for PDF, TXT, and Markdown.
- Fixed and recursive chunking options.
- Local embeddings with PostgreSQL/pgvector storage.
- Heuristic evaluation mode for offline scoring.
- Full RAG mode with provider-backed generation and judge evaluation.
- Redis + RQ queue for durable full-mode benchmark runs.
- Run detail view with retrieval hits, diagnosis, timeline, and run diff.
- Dashboard analytics for run counts, latency distributions, failure breakdowns, and config comparison confidence.
- Dataset, query case, and pipeline config registry.
- Backend, frontend, and E2E test suites documented in the repo.

## Tech Stack

| Area | Technology |
|---|---|
| Backend | FastAPI, SQLAlchemy async, Alembic, Pydantic settings |
| Frontend | React, TypeScript, Vite, React Router |
| Data | PostgreSQL 16, pgvector, HNSW index |
| Queue | Redis, RQ worker |
| AI / Evaluation | sentence-transformers, provider-backed generation and judge modes |
| Testing | pytest, Vitest, React Testing Library, Playwright |
| DevOps | Docker Compose |

## Architecture

```text
React + Vite SPA
   |
   | /api proxy
   v
FastAPI backend
   |        |            |
   |        |            +--> Provider-backed generation / judge mode
   |        +--> Redis + RQ worker for queued full runs
   |
   +--> PostgreSQL + pgvector
```

Ingest path:

```text
Upload -> Parse -> Chunk -> Embed -> Store chunks in pgvector
```

Benchmark path:

```text
Query + config -> Retrieve chunks -> Evaluate -> Persist trace -> Dashboard / run detail
```

Full-mode path:

```text
Query + config -> Queue job -> Retrieve -> Generate -> Judge -> Persist trace
```

## Project Structure

```text
ContextLens/
|-- backend/          # FastAPI app, models, migrations, scripts, pytest tests
|-- frontend/         # React/Vite UI, unit tests, Playwright specs
|-- docs/             # Architecture, decisions, deployment, benchmark notes
|-- docker-compose.yml
|-- .env.example
`-- README.md
```

## Environment Variables

Copy `.env.example` to `.env` and keep real secrets local.

Important variables:

```env
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5433/contextlens
REDIS_URL=redis://localhost:6379/0
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
LLM_PROVIDER=<provider-name>
OPENAI_API_KEY=
CLAUDE_API_KEY=
EMBEDDING_MODEL_NAME=all-MiniLM-L6-v2
GENERATION_MODEL_NAME=<generation-model>
EVALUATION_MODEL_NAME=<evaluation-model>
```

Heuristic mode does not require an external LLM key. Full mode requires the provider key matching the configured provider.

## Run Locally

Prerequisites:

- Docker and Docker Compose
- Node.js 18+
- Python 3.11+

```bash
git clone https://github.com/samarthshete/ContextLens.git
cd ContextLens
cp .env.example .env
docker compose up --build -d
docker compose exec backend alembic upgrade head
```

Seed and run a heuristic benchmark:

```bash
docker compose exec backend python scripts/seed_benchmark.py
docker compose exec backend python scripts/run_benchmark.py --eval-mode heuristic
```

Start the frontend:

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173.

## Testing

Backend:

```bash
cd backend
pytest
```

Frontend:

```bash
cd frontend
npm run test
```

E2E:

```bash
cd frontend
npx playwright install
npm run test:e2e
```

## Technical Decisions

- Use pgvector so trace storage and vector search stay in one relational database.
- Keep the diagnosis layer deterministic and inspectable rather than adding another opaque model call.
- Separate heuristic and full evaluator metrics so offline and model-backed runs are not blended into misleading averages.
- Use Redis/RQ for long-running full-mode jobs so API restarts do not automatically discard queued work.

## Limitations

- Local benchmark results are directional and depend on data, config, machine, and sample size.
- Full evaluation mode requires external provider credentials.
- The current app is built for evaluation/debugging workflows, not as a public chatbot endpoint.

## Future Improvements

- Authentication and team workspaces.
- Hybrid retrieval and reranking.
- Exportable run reports.
- Managed cloud deployment hardening.
- Richer run diff views.

## License

MIT. See `LICENSE`.
