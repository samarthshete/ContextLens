"""DATABASE_URL coercion for managed Postgres URLs (e.g. Render ``postgresql://``)."""

import pytest

from app.config import Settings, normalize_async_database_url


def test_normalize_async_database_url_variants():
    assert normalize_async_database_url(
        "postgresql://u:p@host:5432/db",
    ) == "postgresql+asyncpg://u:p@host:5432/db"
    assert normalize_async_database_url(
        "postgres://u:p@host:5432/db",
    ) == "postgresql+asyncpg://u:p@host:5432/db"
    u = "postgresql+asyncpg://u:p@host:5432/db"
    assert normalize_async_database_url(u) == u


def test_settings_coerces_render_style_url(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    s = Settings(database_url="postgresql://user:pass@dpg.internal:5432/contextlens")
    assert s.database_url == "postgresql+asyncpg://user:pass@dpg.internal:5432/contextlens"
