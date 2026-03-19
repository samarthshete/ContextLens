"""API routes."""

from fastapi import APIRouter

from app.api.chunks import router as chunks_router
from app.api.documents import router as documents_router
from app.api.retrieval import router as retrieval_router

router = APIRouter()

router.include_router(documents_router, prefix="/documents", tags=["documents"])
router.include_router(chunks_router, prefix="/chunks", tags=["chunks"])
router.include_router(retrieval_router, prefix="/retrieval", tags=["retrieval"])
