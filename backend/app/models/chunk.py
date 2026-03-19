"""Chunk model."""

from pgvector.sqlalchemy import Vector
from sqlalchemy import ForeignKey, Integer, Text, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

# all-MiniLM-L6-v2 produces 384-dimensional embeddings.
EMBEDDING_DIM = 384


class Chunk(Base):
    """Represents a chunk of text from a document."""

    __tablename__ = "chunks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    content: Mapped[str] = mapped_column(Text, nullable=False)

    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)

    # Needed for traceability + evaluation later
    start_char: Mapped[int] = mapped_column(Integer, nullable=False)
    end_char: Mapped[int] = mapped_column(Integer, nullable=False)

    metadata_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # pgvector embedding — nullable so existing rows and failed embeddings are ok.
    embedding = mapped_column(Vector(EMBEDDING_DIM), nullable=True)

    document = relationship("Document", back_populates="chunks")

    __table_args__ = (
        Index("idx_chunks_document_index", "document_id", "chunk_index"),
    )
