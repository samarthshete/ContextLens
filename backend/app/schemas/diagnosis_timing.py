"""API shapes for diagnosis timing experiments."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class DiagnosisTimingSessionCreate(BaseModel):
    mode: Literal["manual", "assisted"]
    started_at: datetime | None = None
    session_key: str | None = Field(None, max_length=256)
    synthetic: bool = False


class DiagnosisTimingSessionPatch(BaseModel):
    first_meaningful_insight_at: datetime | None = None
    completed_at: datetime | None = None
    resolution_label: str | None = Field(None, max_length=128)
    notes: str | None = None


class DiagnosisTimingSessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    run_id: int
    mode: str
    started_at: datetime
    first_meaningful_insight_at: datetime | None = None
    completed_at: datetime | None = None
    resolution_label: str | None = None
    notes: str | None = None
    session_key: str | None = None
    synthetic: bool = False
    created_at: datetime
