"""Single-source latency distribution aggregates over ``runs`` (read-only).

Uses PostgreSQL ``percentile_cont`` ordered-set aggregates — same semantics as
``GET /runs/dashboard-analytics`` latency sections. All values come from persisted
``runs.*_latency_ms`` columns; no estimation or client-derived data.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Run
from app.schemas.dashboard_analytics import LatencyDistribution


def _f(v: object | None) -> float | None:
    if v is None:
        return None
    return float(v) if not isinstance(v, float) else v


async def get_phase_latency_distribution(
    session: AsyncSession,
    column: Any,
) -> LatencyDistribution:
    """Min/max/avg/median (P50)/P95 and count for one ``Run`` latency column.

    Rows with NULL for that column are excluded from all aggregates (count is
    non-null rows only). When count is 0, returns an empty ``LatencyDistribution``.
    """
    stmt = select(
        func.count().filter(column.isnot(None)).label("cnt"),
        func.min(column).label("min_v"),
        func.max(column).label("max_v"),
        func.avg(column).label("avg_v"),
        func.percentile_cont(0.5).within_group(column).label("median_v"),
        func.percentile_cont(0.95).within_group(column).label("p95_v"),
    ).select_from(Run)
    row = (await session.execute(stmt)).one()
    cnt = int(row.cnt)
    if cnt == 0:
        return LatencyDistribution()
    return LatencyDistribution(
        count=cnt,
        min_ms=_f(row.min_v),
        max_ms=_f(row.max_v),
        avg_ms=_f(row.avg_v),
        median_ms=_f(row.median_v),
        p95_ms=_f(row.p95_v),
    )
