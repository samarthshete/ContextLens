"""Shared test fixtures.

Tests run against the real database (requires Docker postgres + pgvector).
Each test gets a clean slate via the ``cleanup_db`` autouse fixture.
"""

import io

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.database import async_session_maker
from app.main import app


@pytest.fixture
async def client():
    """Async HTTP client wired to the FastAPI app (no network)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture(autouse=True)
async def cleanup_db():
    """Delete all rows after each test so tests are isolated."""
    yield
    async with async_session_maker() as session:
        await session.execute(text("DELETE FROM chunks"))
        await session.execute(text("DELETE FROM documents"))
        await session.commit()


def make_upload(filename: str, content: str | bytes) -> dict:
    """Build the ``files`` dict for httpx multipart upload."""
    if isinstance(content, str):
        content = content.encode()
    return {"file": (filename, io.BytesIO(content), "application/octet-stream")}
