"""Pipeline configuration for runs (chunking, top_k, embedding model, etc.)."""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class PipelineConfig(Base):
    """Snapshot of pipeline parameters referenced by runs."""

    __tablename__ = "pipeline_configs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(128), nullable=False)
    chunk_strategy: Mapped[str] = mapped_column(String(32), nullable=False)
    chunk_size: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_overlap: Mapped[int] = mapped_column(Integer, nullable=False)
    top_k: Mapped[int] = mapped_column(Integer, nullable=False)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    runs = relationship("Run", back_populates="pipeline_config")
