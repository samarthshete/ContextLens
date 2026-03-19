"""Retrieval API endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.retrieval import SearchRequest, SearchResponse
from app.services.retrieval import search_chunks

router = APIRouter()


@router.post("/search", response_model=SearchResponse)
async def search(body: SearchRequest, db: AsyncSession = Depends(get_db)):
    """Semantic search over chunk embeddings."""
    try:
        results = await search_chunks(
            query=body.query,
            db=db,
            top_k=body.top_k,
            document_id=body.document_id,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="Search failed. The embedding model may not be loaded.",
        ) from exc
    return SearchResponse(query=body.query, results=results)
