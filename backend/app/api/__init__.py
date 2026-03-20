"""API routes."""

from fastapi import APIRouter

from app.api.chunks import router as chunks_router
from app.api.datasets import router as datasets_router
from app.api.documents import router as documents_router
from app.api.pipeline_configs import router as pipeline_configs_router
from app.api.query_cases import router as query_cases_router
from app.api.retrieval import router as retrieval_router
from app.api.runs import router as runs_router

router = APIRouter()

router.include_router(documents_router, prefix="/documents", tags=["documents"])
router.include_router(chunks_router, prefix="/chunks", tags=["chunks"])
router.include_router(retrieval_router, prefix="/retrieval", tags=["retrieval"])
router.include_router(datasets_router, prefix="/datasets", tags=["datasets"])
router.include_router(query_cases_router, prefix="/query-cases", tags=["query-cases"])
router.include_router(pipeline_configs_router, prefix="/pipeline-configs", tags=["pipeline-configs"])
router.include_router(runs_router, prefix="/runs", tags=["runs"])
