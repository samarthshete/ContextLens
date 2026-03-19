from collections.abc import AsyncGenerator

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings

engine = create_async_engine(
    settings.database_url,
    echo=False,
)

async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield a session. Routes own commit/rollback explicitly.

    - Write routes call ``await session.commit()``.
    - Read routes never commit (implicit txn is rolled back on close).
    - On exception the session is rolled back before propagating.
    """
    async with async_session_maker() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def init_db() -> None:
    """Verify DB connectivity on startup.

    Schema is owned exclusively by Alembic — never call create_all here
    so the two sources of truth cannot diverge.
    """
    async with engine.connect() as conn:
        await conn.execute(sa.text("SELECT 1"))
