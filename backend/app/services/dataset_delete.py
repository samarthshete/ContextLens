"""Delete benchmark datasets when safe (no dependent query cases)."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Dataset, QueryCase


class DatasetDeleteConflictError(Exception):
    """Cannot delete: ``query_cases`` still reference this dataset."""

    def __init__(self, detail: str | None = None) -> None:
        self.detail = detail or (
            "Dataset has query cases; remove or reassign them before deleting."
        )
        super().__init__(self.detail)


async def delete_dataset(session: AsyncSession, dataset_id: int) -> bool:
    """Delete dataset if it exists and has no query cases.

    Returns ``True`` if a row was deleted, ``False`` if no such dataset.
    Raises ``DatasetDeleteConflictError`` if any ``query_cases.dataset_id`` matches
    (covers all traced runs, which always reference a query case).
    """

    ds = await session.get(Dataset, dataset_id)
    if ds is None:
        return False

    cnt = (
        await session.execute(
            select(func.count()).select_from(QueryCase).where(QueryCase.dataset_id == dataset_id)
        )
    ).scalar_one()
    if int(cnt) > 0:
        raise DatasetDeleteConflictError()

    await session.delete(ds)
    await session.commit()
    return True
