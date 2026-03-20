"""Tests for the retrieval / semantic search endpoint."""

import pytest
from httpx import AsyncClient

from tests.conftest import make_upload

BASE = "/api/v1"

DOC_A = (
    "Retrieval-Augmented Generation combines retrieval with language model generation. "
    "Dense vector similarity is used to find relevant passages from a corpus."
)

DOC_B = (
    "Photosynthesis converts sunlight into chemical energy. "
    "Chlorophyll in plant cells absorbs light, primarily in the blue and red wavelengths."
)


async def _upload(client: AsyncClient, filename: str, content: str) -> int:
    """Upload a document and return its ID."""
    resp = await client.post(
        f"{BASE}/documents",
        params={"chunk_size": 200},
        files=make_upload(filename, content),
    )
    assert resp.status_code == 201
    return resp.json()["id"]


# --------------------------------------------------------------------------
# Happy path
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_returns_results(client: AsyncClient):
    await _upload(client, "rag.txt", DOC_A)

    resp = await client.post(
        f"{BASE}/retrieval/search",
        json={"query": "What is RAG?", "top_k": 3},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["query"] == "What is RAG?"
    assert len(body["results"]) > 0

    first = body["results"][0]
    assert "chunk_id" in first
    assert "document_id" in first
    assert "content" in first
    assert "chunk_index" in first
    assert "score" in first
    # Score should be positive for a semantically related query.
    assert first["score"] > 0


@pytest.mark.asyncio
async def test_search_scoped_to_document(client: AsyncClient):
    doc_a_id = await _upload(client, "rag.txt", DOC_A)
    await _upload(client, "bio.txt", DOC_B)

    # Search scoped to doc A
    resp = await client.post(
        f"{BASE}/retrieval/search",
        json={"query": "photosynthesis", "top_k": 10, "document_id": doc_a_id},
    )
    assert resp.status_code == 200
    for r in resp.json()["results"]:
        assert r["document_id"] == doc_a_id


@pytest.mark.asyncio
async def test_search_score_ordering(client: AsyncClient):
    """Results should be ordered by descending score (highest similarity first)."""
    await _upload(client, "rag.txt", DOC_A + "\n" + DOC_B)

    resp = await client.post(
        f"{BASE}/retrieval/search",
        json={"query": "dense vector retrieval", "top_k": 10},
    )
    scores = [r["score"] for r in resp.json()["results"]]
    assert scores == sorted(scores, reverse=True)


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_empty_query_rejected(client: AsyncClient):
    resp = await client.post(
        f"{BASE}/retrieval/search",
        json={"query": "", "top_k": 3},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_search_top_k_zero_rejected(client: AsyncClient):
    resp = await client.post(
        f"{BASE}/retrieval/search",
        json={"query": "test", "top_k": 0},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_search_top_k_over_limit_rejected(client: AsyncClient):
    resp = await client.post(
        f"{BASE}/retrieval/search",
        json={"query": "test", "top_k": 101},
    )
    assert resp.status_code == 422


# --------------------------------------------------------------------------
# Edge: no results when DB is empty
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_empty_db_returns_empty(client: AsyncClient):
    resp = await client.post(
        f"{BASE}/retrieval/search",
        json={"query": "anything", "top_k": 5},
    )
    assert resp.status_code == 200
    assert resp.json()["results"] == []


@pytest.mark.asyncio
async def test_search_embedding_failure_returns_503(client: AsyncClient, monkeypatch):
    import app.services.retrieval as retrieval_svc

    def _boom(text: str):
        raise RuntimeError("model not loaded")

    monkeypatch.setattr(retrieval_svc, "embed_text", _boom)

    resp = await client.post(
        f"{BASE}/retrieval/search",
        json={"query": "hello", "top_k": 3},
    )
    assert resp.status_code == 503
