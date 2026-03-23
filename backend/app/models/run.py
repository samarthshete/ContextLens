"""A single RAG run (query → retrieval → generation → evaluation trace)."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Run(Base):
    """Stores per-run latencies when measured by the application."""

    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    query_case_id: Mapped[int] = mapped_column(
        ForeignKey("query_cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    pipeline_config_id: Mapped[int] = mapped_column(
        ForeignKey("pipeline_configs.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")

    retrieval_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    generation_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    evaluation_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    metadata_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    query_case = relationship("QueryCase", back_populates="runs")
    pipeline_config = relationship("PipelineConfig", back_populates="runs")
    retrieval_results = relationship(
        "RetrievalResult",
        back_populates="run",
        cascade="all, delete-orphan",
    )
    evaluation_result = relationship(
        "EvaluationResult",
        back_populates="run",
        uselist=False,
        cascade="all, delete-orphan",
    )
    generation_result = relationship(
        "GenerationResult",
        back_populates="run",
        uselist=False,
        cascade="all, delete-orphan",
    )
