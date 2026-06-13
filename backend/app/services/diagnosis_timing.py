"""CRUD for ``diagnosis_timing_sessions``."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import DiagnosisTimingSession, Run


class DiagnosisSessionNotFoundError(LookupError):
    pass


async def create_diagnosis_session(
    session: AsyncSession,
    *,
    run_id: int,
    mode: str,
    started_at: datetime | None = None,
    session_key: str | None = None,
    synthetic: bool = False,
    commit: bool = True,
) -> DiagnosisTimingSession:
    run = await session.get(Run, run_id)
    if run is None:
        raise ValueError(f"Run id={run_id} not found")
    if mode not in ("manual", "assisted"):
        raise ValueError("mode must be manual or assisted")
    st = started_at or datetime.now(timezone.utc)
    row = DiagnosisTimingSession(
        run_id=run_id,
        mode=mode,
        started_at=st,
        session_key=session_key,
        synthetic=synthetic,
    )
    session.add(row)
    await session.flush()
    if commit:
        await session.commit()
        await session.refresh(row)
    return row


async def patch_diagnosis_session(
    session: AsyncSession,
    *,
    session_id: int,
    first_meaningful_insight_at: datetime | None = None,
    completed_at: datetime | None = None,
    resolution_label: str | None = None,
    notes: str | None = None,
    commit: bool = True,
) -> DiagnosisTimingSession:
    row = await session.get(DiagnosisTimingSession, session_id)
    if row is None:
        raise DiagnosisSessionNotFoundError(session_id)
    if first_meaningful_insight_at is not None:
        row.first_meaningful_insight_at = first_meaningful_insight_at
    if completed_at is not None:
        row.completed_at = completed_at
    if resolution_label is not None:
        row.resolution_label = resolution_label
    if notes is not None:
        row.notes = notes
    await session.flush()
    if commit:
        await session.commit()
        await session.refresh(row)
    return row


async def list_diagnosis_sessions_for_run(
    session: AsyncSession,
    *,
    run_id: int,
) -> list[DiagnosisTimingSession]:
    run = await session.get(Run, run_id)
    if run is None:
        raise ValueError(f"Run id={run_id} not found")
    stmt = (
        select(DiagnosisTimingSession)
        .where(DiagnosisTimingSession.run_id == run_id)
        .order_by(DiagnosisTimingSession.id.asc())
    )
    return list((await session.execute(stmt)).scalars().all())
