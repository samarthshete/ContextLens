"""Response for POST /runs/{run_id}/requeue."""

from pydantic import BaseModel, Field


class RunRequeueResponse(BaseModel):
    run_id: int
    status: str = Field(description="Run row status after enqueue (unchanged until worker progresses).")
    job_id: str = Field(description="RQ job id for the new ``contextlens_full_run`` job.")
