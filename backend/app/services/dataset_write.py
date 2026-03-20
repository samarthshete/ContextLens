"""Create / update benchmark datasets."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Dataset


async def create_dataset(
    session: AsyncSession,
    *,
    name: str,
    description: str | None = None,
    metadata_json: dict[str, Any] | None = None,
) -> Dataset:
    row = Dataset(name=name, description=description, metadata_json=metadata_json)
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def update_dataset(
    session: AsyncSession,
    dataset_id: int,
    *,
    name: str | None = None,
    description: str | None = None,
    metadata_json: dict[str, Any] | None = None,
    fields_set: frozenset[str] | None = None,
) -> Dataset | None:
    """Apply only keys present in ``fields_set`` (from ``model_fields_set``). Missing row → ``None``."""

    row = await session.get(Dataset, dataset_id)
    if row is None:
        return None

    fs = fields_set or frozenset()
    if "name" in fs and name is not None:
        row.name = name
    if "description" in fs:
        row.description = description
    if "metadata_json" in fs:
        row.metadata_json = metadata_json

    await session.commit()
    await session.refresh(row)
    return row
