from collections.abc import AsyncGenerator

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings

engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=True,
)

async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield a session and close it when the request ends.

    Does **not** commit or roll back — callers own transactions:

    - Write routes/services call ``await session.commit()`` after successful work.
    - Write routes call ``await session.rollback()`` before recovery commits when needed.
    - Read-only routes rely on session close to roll back the implicit transaction.

    Mixing auto-commit inside this dependency with explicit commits in routes is avoided.
    """
    async with async_session_maker() as session:
        yield session


async def init_db() -> None:
    """Verify DB connectivity on startup.

    Schema is owned exclusively by Alembic — never call create_all here
    so the two sources of truth cannot diverge.
    """
    async with engine.connect() as conn:
        await conn.execute(sa.text("SELECT 1"))
