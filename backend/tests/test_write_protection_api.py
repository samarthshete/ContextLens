"""Optional write-key middleware and public meta routes."""

from __future__ import annotations

import pytest

from app.config import settings
from app.main import _validate_production_config


@pytest.fixture
def write_key_enabled():
    prev = settings.contextlens_write_key
    settings.contextlens_write_key = "test-secret-key"
    yield
    settings.contextlens_write_key = prev


@pytest.mark.asyncio
async def test_get_meta_shows_write_protection_off_by_default(client):
    r = await client.get("/api/v1/meta")
    assert r.status_code == 200
    data = r.json()
    assert data.get("write_protection") is False
    assert "app_env" in data


@pytest.mark.asyncio
async def test_get_meta_when_write_key_set(client, write_key_enabled):
    r = await client.get("/api/v1/meta")
    assert r.status_code == 200
    assert r.json().get("write_protection") is True


@pytest.mark.asyncio
async def test_health_includes_write_protection_flag(client, write_key_enabled):
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json().get("write_protection") is True


@pytest.mark.asyncio
async def test_post_forbidden_without_write_key(client, write_key_enabled):
    r = await client.post("/api/v1/datasets", json={"name": "blocked-dataset"})
    assert r.status_code == 403
    assert r.json().get("detail") == "write_key_required"


@pytest.mark.asyncio
async def test_post_succeeds_with_write_key_header(client, write_key_enabled):
    r = await client.post(
        "/api/v1/datasets",
        json={"name": "wk-ok-dataset"},
        headers={"X-ContextLens-Write-Key": "test-secret-key"},
    )
    assert r.status_code == 201
    assert r.json()["name"] == "wk-ok-dataset"


@pytest.mark.asyncio
async def test_get_runs_allowed_without_write_key(client, write_key_enabled):
    r = await client.get("/api/v1/runs")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_verify_write_key_endpoint(client, write_key_enabled):
    bad = await client.post(
        "/api/v1/meta/verify-write-key",
        headers={"X-ContextLens-Write-Key": "nope"},
    )
    assert bad.status_code == 403

    ok = await client.post(
        "/api/v1/meta/verify-write-key",
        headers={"X-ContextLens-Write-Key": "test-secret-key"},
    )
    assert ok.status_code == 200
    assert ok.json() == {"ok": True}


def test_production_config_requires_write_key(monkeypatch):
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "contextlens_write_key", "")
    monkeypatch.setattr(settings, "cors_origins", "https://app.example.com")
    with pytest.raises(RuntimeError, match="CONTEXTLENS_WRITE_KEY"):
        _validate_production_config()


def test_production_config_rejects_cors_wildcard(monkeypatch):
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "contextlens_write_key", "secret")
    monkeypatch.setattr(settings, "cors_origins", "*")
    with pytest.raises(RuntimeError, match="CORS_ORIGINS"):
        _validate_production_config()
