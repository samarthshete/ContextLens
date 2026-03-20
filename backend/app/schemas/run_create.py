"""Request/response for inline benchmark run creation (HTTP).

Primary keys for ``query_cases``, ``pipeline_configs``, and ``runs`` are **integer**
autoincrement IDs (see Alembic migrations), matching ``GET /api/v1/runs/{run_id}``.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class RunCreateRequest(BaseModel):
    query_case_id: int = Field(..., ge=1, description="``query_cases.id``")
    pipeline_config_id: int = Field(..., ge=1, description="``pipeline_configs.id``")
    eval_mode: Literal["heuristic", "full"] = "heuristic"
    document_id: int | None = Field(
        None,
        ge=1,
        description="Optional ``documents.id`` — scope retrieval to this document (same as ``search_chunks``).",
    )


class RunCreateResponse(BaseModel):
    run_id: int = Field(..., description="``runs.id`` after execution")
    status: str
    eval_mode: str
    job_id: str | None = Field(
        None,
        description="RQ job id when ``eval_mode=full`` (omit for heuristic).",
    )
