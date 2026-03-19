"""Retrieval service — vector similarity search over chunks."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Chunk
from app.services.embedder import embed_text


async def search_chunks(
    query: str,
    db: AsyncSession,
    top_k: int = 5,
    document_id: int | None = None,
) -> list[dict]:
    """Embed *query*, find the closest chunks by cosine distance, return top_k.

    Returns a list of dicts with keys:
        chunk_id, document_id, content, chunk_index, start_char, end_char, score
    """
    query_vec = embed_text(query)

    # pgvector cosine distance operator: <=> returns distance in [0, 2].
    # score = 1 - distance  →  1.0 = identical, 0.0 = orthogonal.
    distance = Chunk.embedding.cosine_distance(query_vec)

    stmt = (
        select(
            Chunk.id,
            Chunk.document_id,
            Chunk.content,
            Chunk.chunk_index,
            Chunk.start_char,
            Chunk.end_char,
            (1 - distance).label("score"),
        )
        .where(Chunk.embedding.is_not(None))
        .order_by(distance)
        .limit(top_k)
    )

    if document_id is not None:
        stmt = stmt.where(Chunk.document_id == document_id)

    rows = (await db.execute(stmt)).all()

    return [
        {
            "chunk_id": row.id,
            "document_id": row.document_id,
            "content": row.content,
            "chunk_index": row.chunk_index,
            "start_char": row.start_char,
            "end_char": row.end_char,
            "score": round(float(row.score), 6),
        }
        for row in rows
    ]
