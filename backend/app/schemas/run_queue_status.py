"""Response for GET /runs/{run_id}/queue-status."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class RunQueueStatusResponse(BaseModel):
    """Queue / lock inspection for durable full runs (best-effort RQ scan)."""

    run_id: int
    run_status: str
    pipeline: Literal["heuristic", "full"] = Field(
        description="Inferred from persisted trace rows (same heuristic as requeue eligibility).",
    )
    job_id: str | None = Field(
        default=None,
        description="RQ job id if found in queue registries for this run_id (not stored on the run row).",
    )
    rq_job_status: str | None = Field(
        default=None,
        description="RQ job status when a job is found (e.g. queued, started, finished).",
    )
    lock_present: bool = Field(
        description="True if the full-run Redis lock key exists for this run_id.",
    )
    requeue_eligible: bool = Field(
        description="True if POST /requeue would pass structural checks and no worker lock is held. "
        "Does not verify LLM API key (OpenAI/Anthropic per LLM_PROVIDER) or enqueue Redis.",
    )
    detail: str | None = Field(
        default=None,
        description="Why requeue is not structurally eligible, or why lock blocks requeue.",
    )
