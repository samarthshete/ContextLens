"""List / fetch pipeline configs."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PipelineConfig


async def list_pipeline_configs(session: AsyncSession) -> list[PipelineConfig]:
    stmt = select(PipelineConfig).order_by(PipelineConfig.id.asc())
    res = await session.execute(stmt)
    return list(res.scalars().all())


async def get_pipeline_config_by_id(session: AsyncSession, pipeline_config_id: int) -> PipelineConfig | None:
    return await session.get(PipelineConfig, pipeline_config_id)
