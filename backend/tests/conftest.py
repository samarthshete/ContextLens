"""Shared test fixtures.

Tests run against the real database (requires Docker postgres + pgvector).
Each test gets a clean slate via the ``cleanup_db`` autouse fixture.
"""

import asyncio
import io

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.database import engine
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
    # Let ASGI dependency cleanup finish before grabbing a connection from the pool.
    await asyncio.sleep(0.01)
    async with engine.begin() as conn:
        # Trace / benchmark tables first (FK order), then ingestion.
        for stmt in (
            "DELETE FROM evaluation_results",
            "DELETE FROM retrieval_results",
            "DELETE FROM generation_results",
            "DELETE FROM runs",
            "DELETE FROM query_cases",
            "DELETE FROM datasets",
            "DELETE FROM pipeline_configs",
            "DELETE FROM chunks",
            "DELETE FROM documents",
        ):
            await conn.execute(text(stmt))


def make_upload(filename: str, content: str | bytes) -> dict:
    """Build the ``files`` dict for httpx multipart upload."""
    if isinstance(content, str):
        content = content.encode()
    return {"file": (filename, io.BytesIO(content), "application/octet-stream")}
