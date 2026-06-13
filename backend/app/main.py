import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.api import router as api_router
from app.config import settings
from app.database import init_db
from app.middleware.write_protection import WriteProtectionMiddleware
from app.request_context import REQUEST_ID_HEADER, new_request_id, reset_request_id, set_request_id

logger = logging.getLogger(__name__)


def error_payload(
    *,
    code: str,
    message: str,
    retryable: bool,
    request_id: str,
    detail: Any | None = None,
) -> dict[str, Any]:
    """Standard API error response; ``detail`` is kept for old clients/tests."""
    return {
        "detail": detail if detail is not None else message,
        "error": {
            "code": code,
            "message": message,
            "retryable": retryable,
            "request_id": request_id,
        },
    }


def _message_from_detail(detail: Any) -> str:
    if isinstance(detail, str):
        return detail
    if isinstance(detail, list):
        return "Invalid request."
    if detail is None:
        return "Request failed."
    return str(detail)


def _error_code_for_status(status_code: int) -> str:
    return {
        400: "bad_request",
        401: "unauthorized",
        403: "forbidden",
        404: "not_found",
        409: "conflict",
        413: "payload_too_large",
        422: "validation_error",
        502: "upstream_llm_error",
        503: "service_unavailable",
    }.get(status_code, "internal_error" if status_code >= 500 else "request_failed")


def _retryable_for_status(status_code: int) -> bool:
    return status_code in {408, 429, 500, 502, 503, 504}


def _request_id_from_request(request: Request) -> str:
    return getattr(request.state, "request_id", None) or new_request_id()


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER) or new_request_id()
        request.state.request_id = request_id
        token = set_request_id(request_id)
        try:
            response = await call_next(request)
        except Exception:
            logger.exception(
                "request failed request_id=%s method=%s path=%s",
                request_id,
                request.method,
                request.url.path,
            )
            raise
        finally:
            reset_request_id(token)
        response.headers[REQUEST_ID_HEADER] = request_id
        logger.info(
            "request complete request_id=%s method=%s path=%s status=%s",
            request_id,
            request.method,
            request.url.path,
            response.status_code,
        )
        return response


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


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    request_id = _request_id_from_request(request)
    message = _message_from_detail(exc.detail)
    body = error_payload(
        code=_error_code_for_status(exc.status_code),
        message=message,
        retryable=_retryable_for_status(exc.status_code),
        request_id=request_id,
        detail=exc.detail,
    )
    return JSONResponse(status_code=exc.status_code, content=jsonable_encoder(body), headers={REQUEST_ID_HEADER: request_id})


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    request_id = _request_id_from_request(request)
    body = error_payload(
        code="validation_error",
        message="Invalid request.",
        retryable=False,
        request_id=request_id,
        detail=exc.errors(),
    )
    return JSONResponse(status_code=422, content=jsonable_encoder(body), headers={REQUEST_ID_HEADER: request_id})


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = _request_id_from_request(request)
    logger.exception("unhandled exception request_id=%s path=%s", request_id, request.url.path)
    body = error_payload(
        code="internal_error",
        message="Internal server error.",
        retryable=True,
        request_id=request_id,
    )
    return JSONResponse(status_code=500, content=jsonable_encoder(body), headers={REQUEST_ID_HEADER: request_id})


# Inner middleware runs first on request: write protection, then CORS outer.
app.add_middleware(WriteProtectionMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestIDMiddleware)


@app.get("/health")
async def health() -> dict[str, str | bool]:
    return {
        "status": "ok",
        "write_protection": bool((settings.contextlens_write_key or "").strip()),
    }


app.include_router(api_router, prefix="/api/v1", tags=["api"])