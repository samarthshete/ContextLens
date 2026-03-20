"""Paginated run listing."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class RunListItem(BaseModel):
    run_id: int
    status: str
    created_at: datetime
    dataset_id: int
    query_case_id: int
    pipeline_config_id: int
    query_text: str
    retrieval_latency_ms: int | None = None
    generation_latency_ms: int | None = None
    evaluation_latency_ms: int | None = None
    total_latency_ms: int | None = None
    evaluator_type: Literal["heuristic", "llm", "none"] = "none"
    has_evaluation: bool = False


class RunListResponse(BaseModel):
    items: list[RunListItem]
    total: int
    limit: int
    offset: int
