"""Evaluation outcome for a run."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Numeric, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class EvaluationResult(Base):
    """Scores, failure type, judge usage, and measured cost for one run."""

    __tablename__ = "evaluation_results"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("runs.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    faithfulness: Mapped[float | None] = mapped_column(Float, nullable=True)
    completeness: Mapped[float | None] = mapped_column(Float, nullable=True)
    retrieval_relevance: Mapped[float | None] = mapped_column(Float, nullable=True)
    context_coverage: Mapped[float | None] = mapped_column(Float, nullable=True)
    groundedness: Mapped[float | None] = mapped_column(Float, nullable=True)

    failure_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    used_llm_judge: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(14, 6), nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    run = relationship("Run", back_populates="evaluation_result")
