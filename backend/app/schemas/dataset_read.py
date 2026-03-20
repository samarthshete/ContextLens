"""Public read models for benchmark datasets (API responses)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DatasetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="``datasets.id``")
    name: str
    description: str | None = None
    metadata_json: dict[str, Any] | None = None
    created_at: datetime
