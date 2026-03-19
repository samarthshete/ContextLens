# ContextLens — Master Project Document

## 1. Overview

ContextLens is a RAG evaluation and debugging platform.

It helps answer:
"My RAG system gave a wrong answer — where did it fail?"

It exposes the full pipeline:
query → retrieval → context → answer → evaluation → failure classification

---

## 2. Core Goal

Make RAG systems:
- observable
- debuggable
- comparable
- measurable

---

## 3. Scope

### IN SCOPE (V1)
- document upload + parsing
- chunking (fixed + recursive)
- embeddings (local)
- vector retrieval (pgvector)
- answer generation (Claude)
- full trace storage
- evaluation + failure classification
- benchmark datasets
- comparison (later phase)
- dashboard

### OUT OF SCOPE
- auth
- billing
- multi-tenant
- plugins
- hybrid retrieval
- reranking (later)
- cloud infra

---

## 4. Frozen Stack

Backend:
- FastAPI
- SQLAlchemy (async)
- Alembic

DB:
- PostgreSQL + pgvector

Frontend:
- React + Vite + TypeScript
- Tailwind

AI:
- Embeddings: all-MiniLM-L6-v2
- LLM: Claude Sonnet

---

## 5. Architecture Flow

1. Upload document
2. Parse text
3. Chunk text
4. Embed chunks
5. Store in DB
6. Query → retrieve top-k
7. Build context
8. Generate answer
9. Store run
10. Evaluate
11. Classify failure

---

## 6. Data Model (9 Tables)

IMPORTANT: use `metadata_json` not `metadata`

Tables:
1. documents
2. chunks
3. datasets
4. query_cases
5. pipeline_configs
6. runs
7. retrieval_results
8. rerank_results (future)
9. evaluation_results

---

## 7. Failure Types

- NO_FAILURE
- RETRIEVAL_MISS
- RETRIEVAL_PARTIAL
- CHUNK_FRAGMENTATION
- CONTEXT_TRUNCATION
- ANSWER_UNSUPPORTED
- ANSWER_INCOMPLETE
- MIXED_FAILURE
- UNKNOWN

NOTE: classification is heuristic, not perfect truth.

---

## 8. API (Core Only First)

System:
- GET /health

Documents:
- POST /api/v1/documents/upload
- GET /api/v1/documents
- GET /api/v1/documents/{id}
- DELETE /api/v1/documents/{id}

Runs:
- POST /api/v1/runs
- GET /api/v1/runs
- GET /api/v1/runs/{id}

Evaluation:
- GET /api/v1/runs/{id}/evaluation

Build endpoints gradually, not all at once.

---

## 9. Phases

Phase 1: foundation  
Phase 2: ingestion + chunking  
Phase 3: embeddings + retrieval  
Phase 4: generation + trace  
Phase 5: evaluation  
Phase 6: datasets  
Phase 7: frontend  
Phase 8: comparison  
Phase 9: polish  

---

## 10. Rules

- Backend correctness > frontend
- Do not expand scope
- Do not add infra early
- Keep system inspectable
- Always store trace