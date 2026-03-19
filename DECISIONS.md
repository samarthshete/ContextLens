# DECISIONS

## Identity
- ContextLens = RAG debugging tool
- NOT a chatbot project

## Backend
- FastAPI
- SQLAlchemy async
- Alembic

## Database
- PostgreSQL + pgvector
- No external vector DB

## Frontend
- React + Vite
- No Next.js

## Models
- Embeddings: all-MiniLM-L6-v2
- LLM: Claude

## Retrieval
- vector only
- no hybrid
- no reranking (later)

## Chunking
- fixed + recursive only for now

## Processing
- BackgroundTasks allowed early
- upgrade later if needed

## Scope
- single user
- no auth
- no billing
- no plugins
- no agents

## Evaluation
- must be explainable
- not only LLM-based

## Docs Rule

PROJECT.md = architecture  
CURRENT_STATE.md = progress  
TASK.md = next step  
DECISIONS.md = constraints  

If something conflicts → follow DECISIONS.md