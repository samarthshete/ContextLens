"""API error envelope and request id contract."""

from __future__ import annotations

import pytest


BASE = "/api/v1"


def _assert_error_envelope(body: dict, *, code: str, retryable: bool, request_id: str) -> None:
    assert "detail" in body
    assert body["error"]["code"] == code
    assert isinstance(body["error"]["message"], str)
    assert body["error"]["retryable"] is retryable
    assert body["error"]["request_id"] == request_id


@pytest.mark.asyncio
async def test_http_exception_errors_include_envelope_and_request_id_header(client):
    request_id = "contract-404"

    resp = await client.get(f"{BASE}/runs/999999", headers={"X-Request-ID": request_id})

    assert resp.status_code == 404
    assert resp.headers["X-Request-ID"] == request_id
    _assert_error_envelope(
        resp.json(),
        code="not_found",
        retryable=False,
        request_id=request_id,
    )


@pytest.mark.asyncio
async def test_validation_errors_include_envelope_and_request_id_header(client):
    request_id = "contract-422"

    resp = await client.post(f"{BASE}/query-cases", json={}, headers={"X-Request-ID": request_id})

    assert resp.status_code == 422
    assert resp.headers["X-Request-ID"] == request_id
    _assert_error_envelope(
        resp.json(),
        code="validation_error",
        retryable=False,
        request_id=request_id,
    )
