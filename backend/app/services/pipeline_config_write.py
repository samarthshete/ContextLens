"""Create / update pipeline configs (retrieval parameters only)."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PipelineConfig


class InvalidPipelineConfigError(ValueError):
    """Semantic checks after applying a patch (e.g. overlap vs chunk size)."""


def _validate_pipeline_row(row: PipelineConfig) -> None:
    if row.chunk_overlap > row.chunk_size:
        raise InvalidPipelineConfigError("chunk_overlap cannot be greater than chunk_size")
    if row.top_k < 1:
        raise InvalidPipelineConfigError("top_k must be at least 1")


async def create_pipeline_config(
    session: AsyncSession,
    *,
    name: str,
    embedding_model: str,
    chunk_strategy: str,
    chunk_size: int,
    chunk_overlap: int,
    top_k: int,
    metadata_json: dict[str, Any] | None = None,
) -> PipelineConfig:
    row = PipelineConfig(
        name=name,
        embedding_model=embedding_model,
        chunk_strategy=chunk_strategy,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        top_k=top_k,
        metadata_json=metadata_json,
    )
    _validate_pipeline_row(row)
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def update_pipeline_config(
    session: AsyncSession,
    pipeline_config_id: int,
    *,
    name: str | None = None,
    embedding_model: str | None = None,
    chunk_strategy: str | None = None,
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
    top_k: int | None = None,
    metadata_json: dict[str, Any] | None = None,
    fields_set: frozenset[str] | None = None,
) -> PipelineConfig | None:
    row = await session.get(PipelineConfig, pipeline_config_id)
    if row is None:
        return None

    fs = fields_set or frozenset()
    if "name" in fs and name is not None:
        row.name = name
    if "embedding_model" in fs and embedding_model is not None:
        row.embedding_model = embedding_model
    if "chunk_strategy" in fs and chunk_strategy is not None:
        row.chunk_strategy = chunk_strategy
    if "chunk_size" in fs and chunk_size is not None:
        row.chunk_size = chunk_size
    if "chunk_overlap" in fs and chunk_overlap is not None:
        row.chunk_overlap = chunk_overlap
    if "top_k" in fs and top_k is not None:
        row.top_k = top_k
    if "metadata_json" in fs:
        row.metadata_json = metadata_json

    _validate_pipeline_row(row)
    await session.commit()
    await session.refresh(row)
    return row
