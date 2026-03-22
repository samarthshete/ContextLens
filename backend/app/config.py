"""Application settings (env / `.env`). See repository `.env.example` and `DECISIONS.md`."""

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def normalize_async_database_url(url: str) -> str:
    """Render/Railway often provide ``postgresql://…``; SQLAlchemy async needs ``postgresql+asyncpg://``."""
    s = url.strip()
    if s.startswith("postgresql+asyncpg://"):
        return s
    if s.startswith("postgresql://"):
        return "postgresql+asyncpg://" + s.removeprefix("postgresql://")
    if s.startswith("postgres://"):
        return "postgresql+asyncpg://" + s.removeprefix("postgres://")
    return s


class Settings(BaseSettings):
    app_name: str = "ContextLens"
    app_env: str = "development"
    debug: bool = False

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/contextlens"
    redis_url: str = "redis://localhost:6379/0"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # Optional: when non-empty, POST/PATCH/DELETE (and other non-GET) under /api/v1 require
    # header X-ContextLens-Write-Key (see docs/DEPLOYMENT.md). Required when APP_ENV=production.
    contextlens_write_key: str = ""
    upload_dir: str = "uploads"

    # Upload limits
    max_upload_size_bytes: int = 50 * 1024 * 1024  # 50 MB
    max_text_length: int = 5_000_000  # 5 million characters
    max_chunks_per_document: int = 10_000

    # Provider selection
    llm_provider: str = "openai"  # "openai" | "anthropic"

    # API keys
    claude_api_key: str = ""
    openai_api_key: str = ""

    # Models
    embedding_model_name: str = "all-MiniLM-L6-v2"
    generation_model_name: str = "gpt-4o-mini"
    evaluation_model_name: str = "gpt-4o-mini"

    # Anthropic pricing (USD per 1M tokens)
    anthropic_input_usd_per_million_tokens: float = 3.0
    anthropic_output_usd_per_million_tokens: float = 15.0

    # OpenAI pricing (USD per 1M tokens)
    openai_input_usd_per_million_tokens: float = 0.15
    openai_output_usd_per_million_tokens: float = 0.60

    @field_validator("database_url", mode="before")
    @classmethod
    def coerce_asyncpg_database_url(cls, v: object) -> object:
        if isinstance(v, str):
            return normalize_async_database_url(v)
        return v

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


settings = Settings()