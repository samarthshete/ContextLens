"""Delete query cases when safe (no runs reference them)."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import QueryCase, Run


class QueryCaseDeleteConflictError(Exception):
    """Cannot delete: ``runs`` still reference this query case."""

    def __init__(self, detail: str | None = None) -> None:
        self.detail = detail or (
            "Query case is referenced by runs; remove or archive runs before deleting."
        )
        super().__init__(self.detail)


async def delete_query_case(session: AsyncSession, query_case_id: int) -> bool:
    """Delete query case if it exists and has no runs.

    Returns ``True`` if deleted, ``False`` if not found.
    Raises ``QueryCaseDeleteConflictError`` if any ``runs.query_case_id`` matches.

    Note: the database FK uses ``ON DELETE CASCADE`` from ``query_cases`` to ``runs``;
    this service blocks deletes when runs exist so trace history is not silently removed.
    """

    qc = await session.get(QueryCase, query_case_id)
    if qc is None:
        return False

    cnt = (
        await session.execute(
            select(func.count()).select_from(Run).where(Run.query_case_id == query_case_id)
        )
    ).scalar_one()
    if int(cnt) > 0:
        raise QueryCaseDeleteConflictError()

    await session.delete(qc)
    await session.commit()
    return True
