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

    pgvector / SQLAlchemy: ``Chunk.embedding.cosine_distance(q)`` compiles to the
    ``<=>`` operator with ``vector_cosine_ops`` (see migration ``idx_chunks_embedding_cosine``).
    For L2-normalized vectors (``normalize_embeddings=True`` in the embedder), this distance
    is ``1 - cosine_similarity``, so ``score = 1 - distance`` equals **cosine similarity**
    in ``[-1, 1]`` (typically positive for related text).

    Returns dicts with:
        chunk_id, document_id, content, chunk_index, start_char, end_char, score
    """
    query_vec = embed_text(query)

    distance = Chunk.embedding.cosine_distance(query_vec)
    similarity = (1 - distance).label("score")

    stmt = (
        select(
            Chunk.id,
            Chunk.document_id,
            Chunk.content,
            Chunk.chunk_index,
            Chunk.start_char,
            Chunk.end_char,
            similarity,
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
