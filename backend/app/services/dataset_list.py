"""List / fetch benchmark datasets."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Dataset


async def list_datasets(session: AsyncSession) -> list[Dataset]:
    """Newest first, then ``id`` for stable tie-break."""
    stmt = select(Dataset).order_by(Dataset.created_at.desc(), Dataset.id.desc())
    res = await session.execute(stmt)
    return list(res.scalars().all())


async def get_dataset_by_id(session: AsyncSession, dataset_id: int) -> Dataset | None:
    return await session.get(Dataset, dataset_id)
