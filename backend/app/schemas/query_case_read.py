"""Public read models for query cases (benchmark questions)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class QueryCaseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="``query_cases.id``")
    dataset_id: int
    query_text: str
    expected_answer: str | None = None
    metadata_json: dict[str, Any] | None = None
