"""Per-request correlation id helpers.

HTTP middleware sets the context variable; worker code may set it from job metadata.
"""

from __future__ import annotations

from contextvars import ContextVar
from uuid import uuid4

REQUEST_ID_HEADER = "X-Request-ID"

_request_id_var: ContextVar[str | None] = ContextVar("contextlens_request_id", default=None)


def new_request_id() -> str:
    return str(uuid4())


def get_request_id() -> str | None:
    return _request_id_var.get()


def set_request_id(request_id: str | None):
    return _request_id_var.set(request_id)


def reset_request_id(token) -> None:
    _request_id_var.reset(token)
