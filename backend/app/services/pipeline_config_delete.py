"""Delete pipeline configs when safe (no runs reference them)."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PipelineConfig, Run


class PipelineConfigDeleteConflictError(Exception):
    """Cannot delete: ``runs`` still reference this pipeline config."""

    def __init__(self, detail: str | None = None) -> None:
        self.detail = detail or (
            "Pipeline config is referenced by runs; cannot delete while runs exist."
        )
        super().__init__(self.detail)


async def delete_pipeline_config(session: AsyncSession, pipeline_config_id: int) -> bool:
    """Delete pipeline config if it exists and has no runs.

    Returns ``True`` if deleted, ``False`` if not found.
    Raises ``PipelineConfigDeleteConflictError`` if any ``runs.pipeline_config_id`` matches.

    Matches DB ``ON DELETE RESTRICT`` on ``runs.pipeline_config_id`` — we check first
    and return **409** instead of an integrity error.
    """

    pc = await session.get(PipelineConfig, pipeline_config_id)
    if pc is None:
        return False

    cnt = (
        await session.execute(
            select(func.count())
            .select_from(Run)
            .where(Run.pipeline_config_id == pipeline_config_id)
        )
    ).scalar_one()
    if int(cnt) > 0:
        raise PipelineConfigDeleteConflictError()

    await session.delete(pc)
    await session.commit()
    return True
