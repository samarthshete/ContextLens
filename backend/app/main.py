from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import router as api_router
from app.config import settings
from app.database import init_db
from app.middleware.write_protection import WriteProtectionMiddleware

logger = logging.getLogger(__name__)


def _validate_production_config() -> None:
    """Fail fast for strict production profile (honest hosted API hardening)."""
    env = (settings.app_env or "").strip().lower()
    if env != "production":
        return
    origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
    if not origins:
        raise RuntimeError("CORS_ORIGINS must list at least one origin when APP_ENV=production")
    if any(o == "*" for o in origins):
        raise RuntimeError("CORS_ORIGINS must not use '*' when APP_ENV=production")
    if not (settings.contextlens_write_key or "").strip():
        raise RuntimeError("CONTEXTLENS_WRITE_KEY is required when APP_ENV=production")


@asynccontextmanager
async def lifespan(app: FastAPI):
    _validate_production_config()
    await init_db()
    if (settings.app_env or "").strip().lower() == "production":
        logger.info(
            "contextlens.startup app_env=production write_protection=%s cors_origins_count=%s",
            bool((settings.contextlens_write_key or "").strip()),
            len([o for o in settings.cors_origins.split(",") if o.strip()]),
        )
    yield


_is_prod = (settings.app_env or "").strip().lower() == "production"

app = FastAPI(
    title=settings.app_name,
    description="RAG evaluation and debugging platform",
    version="0.1.0",
    lifespan=lifespan,
    docs_url=None if _is_prod else "/docs",
    redoc_url=None if _is_prod else "/redoc",
    openapi_url=None if _is_prod else "/openapi.json",
)

# Inner middleware runs first on request: write protection, then CORS outer.
app.add_middleware(WriteProtectionMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict[str, str | bool]:
    return {
        "status": "ok",
        "write_protection": bool((settings.contextlens_write_key or "").strip()),
    }


app.include_router(api_router, prefix="/api/v1", tags=["api"])