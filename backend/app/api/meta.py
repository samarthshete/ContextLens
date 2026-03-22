"""Public deployment / capability metadata (no secrets)."""

from fastapi import APIRouter

from app.config import settings

router = APIRouter()


@router.get("/meta", tags=["system"])
async def api_meta() -> dict[str, bool | str]:
    """Whether write protection is enabled and current app environment label."""
    return {
        "write_protection": bool((settings.contextlens_write_key or "").strip()),
        "app_env": settings.app_env,
    }


@router.post("/meta/verify-write-key", tags=["system"])
async def verify_write_key() -> dict[str, bool]:
    """No-op when reached: middleware already validated ``X-ContextLens-Write-Key``."""
    return {"ok": True}
