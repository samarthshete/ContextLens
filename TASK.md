# CURRENT TASK

## Phase
Phase 1 — Foundation

## Objective
Audit and fix backend scaffold.

## Validate

- docker-compose.yml
- Dockerfile
- pyproject.toml
- main.py
- config.py
- database.py
- models init
- API router

## Output Required

- backend runs
- DB connection works
- /health works
- no crashes

## Constraints

- no new features
- no ingestion yet
- no evaluation yet
- no architecture changes

## Next Step After This

Start Phase 2:
document upload + parsing + chunking

# CURRENT TASK

## Phase
Phase 2 — Document Ingestion + Chunking

## Objective
Implement document upload, parsing, chunk creation, and read endpoints.

## Build Now
- parser.py
- chunker.py
- document schemas
- chunk schemas
- documents API
- chunks API
- router wiring

## Constraints
- no embeddings
- no retrieval
- no evaluation
- no reranking
- no frontend work

## Done When
- upload works
- parsed text stored
- chunks stored
- list/detail/chunk endpoints work