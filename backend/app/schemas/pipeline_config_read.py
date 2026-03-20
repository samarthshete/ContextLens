"""Public read models for pipeline configs (retrieval parameters)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PipelineConfigRead(BaseModel):
    """Retrieval-side parameters stored on ``pipeline_configs`` (eval mode is chosen per run)."""

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="``pipeline_configs.id``")
    name: str
    embedding_model: str
    chunk_strategy: str
    chunk_size: int
    chunk_overlap: int
    top_k: int
    metadata_json: dict[str, Any] | None = None
    created_at: datetime
