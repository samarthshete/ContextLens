from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "ContextLens"
    app_env: str = "development"
    debug: bool = False

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/contextlens"
    # RQ worker + API enqueue (full benchmark jobs)
    redis_url: str = "redis://localhost:6379/0"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    upload_dir: str = "uploads"

    # Upload limits
    max_upload_size_bytes: int = 50 * 1024 * 1024  # 50 MB
    max_text_length: int = 5_000_000  # 5 million characters
    max_chunks_per_document: int = 10_000

    claude_api_key: str = ""
    embedding_model_name: str = "all-MiniLM-L6-v2"
    generation_model_name: str = "claude-3-5-sonnet-latest"
    evaluation_model_name: str = "claude-3-5-sonnet-latest"
    # Rough USD per 1M tokens for cost_usd estimates (set 0 to omit cost). Update to match your invoice.
    anthropic_input_usd_per_million_tokens: float = 3.0
    anthropic_output_usd_per_million_tokens: float = 15.0

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


settings = Settings()