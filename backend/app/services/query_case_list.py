"""List / fetch query cases."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Dataset, QueryCase


class DatasetNotFoundForFilterError(LookupError):
    """``dataset_id`` filter was set but no matching ``datasets`` row."""


async def list_query_cases(
    session: AsyncSession,
    *,
    dataset_id: int | None = None,
) -> list[QueryCase]:
    if dataset_id is not None:
        ds = await session.get(Dataset, dataset_id)
        if ds is None:
            raise DatasetNotFoundForFilterError(dataset_id)

    stmt = select(QueryCase)
    if dataset_id is not None:
        stmt = stmt.where(QueryCase.dataset_id == dataset_id)
    stmt = stmt.order_by(QueryCase.dataset_id.asc(), QueryCase.id.asc())
    res = await session.execute(stmt)
    return list(res.scalars().all())


async def get_query_case_by_id(session: AsyncSession, query_case_id: int) -> QueryCase | None:
    return await session.get(QueryCase, query_case_id)
