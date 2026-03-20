"""Request bodies for pipeline config create / update (registry writes)."""

from __future__ import annotations

from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PipelineConfigCreateRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(..., min_length=1, max_length=256)
    embedding_model: str = Field(..., min_length=1, max_length=128)
    chunk_strategy: str = Field(..., min_length=1, max_length=32)
    chunk_size: int = Field(..., ge=1, le=1_000_000)
    chunk_overlap: int = Field(..., ge=0, le=1_000_000)
    top_k: int = Field(..., ge=1, le=10_000)
    metadata_json: dict[str, Any] | None = None

    @model_validator(mode="after")
    def overlap_lte_chunk_size(self) -> Self:
        if self.chunk_overlap > self.chunk_size:
            raise ValueError("chunk_overlap cannot be greater than chunk_size")
        return self


class PipelineConfigUpdateRequest(BaseModel):
    """PATCH body: only provided fields are applied; final row is validated in the service."""

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str | None = Field(default=None, min_length=1, max_length=256)
    embedding_model: str | None = Field(default=None, min_length=1, max_length=128)
    chunk_strategy: str | None = Field(default=None, min_length=1, max_length=32)
    chunk_size: int | None = Field(default=None, ge=1, le=1_000_000)
    chunk_overlap: int | None = Field(default=None, ge=0, le=1_000_000)
    top_k: int | None = Field(default=None, ge=1, le=10_000)
    metadata_json: dict[str, Any] | None = None

    @model_validator(mode="after")
    def reject_explicit_null_strings(self) -> Self:
        for field in ("name", "embedding_model", "chunk_strategy"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        for field in ("chunk_size", "chunk_overlap", "top_k"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self
