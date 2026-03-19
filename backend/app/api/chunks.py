"""Chunk API endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Chunk
from app.schemas.chunk import ChunkResponse

router = APIRouter()


@router.get("/{chunk_id}", response_model=ChunkResponse)
async def get_chunk(chunk_id: int, db: AsyncSession = Depends(get_db)):
    """Get a chunk by ID."""
    result = await db.execute(select(Chunk).where(Chunk.id == chunk_id))
    chunk = result.scalar_one_or_none()
    if not chunk:
        raise HTTPException(404, "Chunk not found")
    return chunk
