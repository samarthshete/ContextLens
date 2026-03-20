"""Request bodies for benchmark dataset create / update (registry writes)."""

from __future__ import annotations

from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DatasetCreateRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(..., min_length=1, max_length=256, description="``datasets.name``")
    description: str | None = Field(default=None, description="``datasets.description``")
    metadata_json: dict[str, Any] | None = Field(
        default=None,
        description="Optional JSONB on ``datasets`` (not required for benchmarks).",
    )


class DatasetUpdateRequest(BaseModel):
    """PATCH body: only provided fields are applied."""

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str | None = Field(default=None, min_length=1, max_length=256)
    description: str | None = None
    metadata_json: dict[str, Any] | None = None

    @model_validator(mode="after")
    def reject_explicit_null_name(self) -> Self:
        if "name" in self.model_fields_set and self.name is None:
            raise ValueError("name cannot be null")
        return self
