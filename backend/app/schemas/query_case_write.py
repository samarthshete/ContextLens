"""Request bodies for query case create / update (registry writes)."""

from __future__ import annotations

from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class QueryCaseCreateRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    dataset_id: int = Field(..., ge=1, description="Parent ``datasets.id``")
    query_text: str = Field(..., min_length=1, description="``query_cases.query_text``")
    expected_answer: str | None = Field(default=None, description="``query_cases.expected_answer``")
    metadata_json: dict[str, Any] | None = None


class QueryCaseUpdateRequest(BaseModel):
    """PATCH body: only provided fields are applied."""

    model_config = ConfigDict(str_strip_whitespace=True)

    dataset_id: int | None = Field(default=None, ge=1)
    query_text: str | None = Field(default=None, min_length=1)
    expected_answer: str | None = None
    metadata_json: dict[str, Any] | None = None

    @model_validator(mode="after")
    def reject_explicit_nulls(self) -> Self:
        if "dataset_id" in self.model_fields_set and self.dataset_id is None:
            raise ValueError("dataset_id cannot be null")
        if "query_text" in self.model_fields_set and self.query_text is None:
            raise ValueError("query_text cannot be null")
        return self
