"""Shared test fixtures.

Tests run against the real database (requires Docker postgres + pgvector).
Each test gets a clean slate via the ``cleanup_db`` autouse fixture.
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import math

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.database import engine
from app.main import app

# Import sites that bind ``embed_text`` / ``embed_texts`` at load time (patch all).
import app.services.embedder as _embedder_mod  # noqa: E402
import app.services.retrieval as _retrieval_mod  # noqa: E402
import app.services.text_document_ingest as _ingest_mod  # noqa: E402


def _deterministic_normalized_embedding(text: str) -> list[float]:
    """384-d L2-normalized fake vector — no HuggingFace / sentence-transformers download."""
    dim = 384
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    v: list[float] = []
    for i in range(dim):
        b = digest[i % len(digest)]
        perturb = (b / 255.0) * 0.1 - 0.05
        v.append(1.0 + perturb + (i % 17) * 1e-4)
    n = math.sqrt(sum(x * x for x in v))
    return [x / n for x in v]


def _fake_embed_text(text: str) -> list[float]:
    return _deterministic_normalized_embedding(text)


def _fake_embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    return [_deterministic_normalized_embedding(t) for t in texts]


@pytest.fixture(scope="session", autouse=True)
def _deterministic_embedding_backend():
    """Offline-safe tests: document upload + retrieval must not download ST models.

    Failures from missing HF cache / no network (422 on upload, 503 on search) are
    **environmental**, not product regressions. Per-test ``monkeypatch`` on
    ``embed_text`` / ``embed_texts`` still overrides this for targeted error tests.
    """
    _embedder_mod.embed_text = _fake_embed_text
    _embedder_mod.embed_texts = _fake_embed_texts
    _ingest_mod.embed_texts = _fake_embed_texts
    _retrieval_mod.embed_text = _fake_embed_text
    _embedder_mod._get_model.cache_clear()
    yield


@pytest.fixture
async def client():
    """Async HTTP client wired to the FastAPI app (no network)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture(autouse=True)
async def cleanup_db(request):
    """Delete all rows after each test so tests are isolated."""
    yield
    if request.node.get_closest_marker("no_database_cleanup"):
        return
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
