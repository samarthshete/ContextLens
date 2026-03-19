"""Tests for document upload, listing, fetching, and deletion."""

import pytest
from httpx import AsyncClient

from tests.conftest import make_upload

BASE = "/api/v1"

SAMPLE_TEXT = (
    "Retrieval-Augmented Generation combines retrieval with generation.\n"
    "Dense embeddings capture semantic meaning in vector space.\n"
    "Chunking strategies determine retrieval granularity."
)


# --------------------------------------------------------------------------
# Upload — happy path
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upload_valid_txt(client: AsyncClient):
    resp = await client.post(
        f"{BASE}/documents",
        params={"chunk_size": 100, "chunk_overlap": 10},
        files=make_upload("sample.txt", SAMPLE_TEXT),
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "processed"
    assert body["source_type"] == "txt"
    assert body["title"] == "sample.txt"

    # Chunks should exist
    doc_id = body["id"]
    chunks_resp = await client.get(f"{BASE}/documents/{doc_id}/chunks")
    assert chunks_resp.status_code == 200
    chunks = chunks_resp.json()
    assert len(chunks) > 0
    # Every chunk has start_char and end_char
    for c in chunks:
        assert "start_char" in c
        assert "end_char" in c
        assert c["end_char"] > c["start_char"]


@pytest.mark.asyncio
async def test_upload_markdown(client: AsyncClient):
    resp = await client.post(
        f"{BASE}/documents",
        files=make_upload("readme.md", "# Title\n\nSome content here."),
    )
    assert resp.status_code == 201
    assert resp.json()["source_type"] == "md"


# --------------------------------------------------------------------------
# Upload — validation errors
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upload_invalid_file_type(client: AsyncClient):
    resp = await client.post(
        f"{BASE}/documents",
        files=make_upload("data.csv", "a,b,c"),
    )
    assert resp.status_code == 400
    assert "Unsupported file type" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_upload_overlap_exceeds_chunk_size(client: AsyncClient):
    resp = await client.post(
        f"{BASE}/documents",
        params={"chunk_size": 50, "chunk_overlap": 50},
        files=make_upload("sample.txt", SAMPLE_TEXT),
    )
    assert resp.status_code == 400
    assert "chunk_overlap" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_upload_chunk_size_zero(client: AsyncClient):
    """chunk_size must be > 0 (enforced by Query(gt=0))."""
    resp = await client.post(
        f"{BASE}/documents",
        params={"chunk_size": 0},
        files=make_upload("sample.txt", SAMPLE_TEXT),
    )
    assert resp.status_code == 422  # FastAPI validation


@pytest.mark.asyncio
async def test_upload_file_too_large(client: AsyncClient, monkeypatch):
    """Files exceeding max_upload_size_bytes are rejected with 413."""
    from app import config

    monkeypatch.setattr(config.settings, "max_upload_size_bytes", 10)
    resp = await client.post(
        f"{BASE}/documents",
        files=make_upload("big.txt", "x" * 100),
    )
    assert resp.status_code == 413
    assert "too large" in resp.json()["detail"]


# --------------------------------------------------------------------------
# Failure path — embedding failure marks document "failed"
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upload_embedding_failure_marks_failed(client: AsyncClient, monkeypatch):
    """If embed_texts raises, document status must be 'failed'."""
    from app.services import embedder

    def _boom(texts):
        raise RuntimeError("GPU exploded")

    monkeypatch.setattr(embedder, "embed_texts", _boom)

    resp = await client.post(
        f"{BASE}/documents",
        files=make_upload("sample.txt", SAMPLE_TEXT),
    )
    assert resp.status_code == 422

    # The document row should exist with status="failed".
    docs_resp = await client.get(f"{BASE}/documents")
    docs = docs_resp.json()
    failed = [d for d in docs if d["status"] == "failed"]
    assert len(failed) == 1


# --------------------------------------------------------------------------
# List / Get / Delete
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_documents(client: AsyncClient):
    # Upload two docs
    await client.post(
        f"{BASE}/documents", files=make_upload("a.txt", "First doc.")
    )
    await client.post(
        f"{BASE}/documents", files=make_upload("b.txt", "Second doc.")
    )

    resp = await client.get(f"{BASE}/documents")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


@pytest.mark.asyncio
async def test_get_document_not_found(client: AsyncClient):
    resp = await client.get(f"{BASE}/documents/99999")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_document_removes_chunks(client: AsyncClient):
    # Upload
    resp = await client.post(
        f"{BASE}/documents",
        params={"chunk_size": 80},
        files=make_upload("sample.txt", SAMPLE_TEXT),
    )
    doc_id = resp.json()["id"]

    # Chunks exist
    chunks_resp = await client.get(f"{BASE}/documents/{doc_id}/chunks")
    assert len(chunks_resp.json()) > 0

    # Delete
    del_resp = await client.delete(f"{BASE}/documents/{doc_id}")
    assert del_resp.status_code == 204

    # Document gone
    get_resp = await client.get(f"{BASE}/documents/{doc_id}")
    assert get_resp.status_code == 404

    # Chunks gone (document returns 404 so we can't fetch via /documents/X/chunks)
    chunks_after = await client.get(f"{BASE}/documents/{doc_id}/chunks")
    assert chunks_after.status_code == 404
