"""Runs API: create (inline heuristic or async full benchmark), list, config comparison, detail."""

from typing import Literal

import anthropic
from openai import APIError as OpenAIAPIError
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.queue.full_run import enqueue_full_benchmark_run
from app.schemas.config_comparison import ConfigComparisonResponse
from app.schemas.dashboard_analytics import DashboardAnalyticsResponse
from app.schemas.dashboard_summary import DashboardSummaryResponse
from app.schemas.run_create import RunCreateRequest, RunCreateResponse
from app.schemas.run_detail import RunDetailResponse
from app.schemas.run_list import RunListResponse
from app.schemas.run_queue_status import RunQueueStatusResponse
from app.schemas.run_requeue import RunRequeueResponse
from app.services import trace_persistence as tp
from app.services.config_comparison import compare_pipeline_configs
from app.services.run_create import (
    DocumentNotFoundError,
    FullModeNotConfiguredError,
    PipelineConfigNotFoundError,
    QueryCaseNotFoundError,
    create_and_execute_run_from_ids,
    validate_run_create_prerequisites,
)
from app.services.run_detail import get_run_detail
from app.services.run_lifecycle import STATUS_RUNNING
from app.services.dashboard_analytics import get_dashboard_analytics
from app.services.dashboard_summary import get_dashboard_summary
from app.services.run_list import list_runs
from app.services.run_queue_status import get_run_queue_status
from app.services.run_requeue import (
    RunNotFoundError,
    RunRequeueConflictError,
    requeue_full_run,
)

router = APIRouter()

@router.get(
    "/dashboard-summary",
    response_model=DashboardSummaryResponse,
    summary="Dashboard aggregates (runs, latency, cost, failures, recent)",
)
async def dashboard_summary_endpoint(
    db: AsyncSession = Depends(get_db),
) -> DashboardSummaryResponse:
    """Read-only aggregates for UI observability (no run mutation)."""
    return await get_dashboard_summary(db)


@router.get(
    "/dashboard-analytics",
    response_model=DashboardAnalyticsResponse,
    summary="Dashboard analytics (time series, latency distribution, failures, config insights)",
)
async def dashboard_analytics_endpoint(
    db: AsyncSession = Depends(get_db),
) -> DashboardAnalyticsResponse:
    """Richer analytics layer: time series, latency distribution, failure analysis, config insights."""
    return await get_dashboard_analytics(db)


@router.get("/config-comparison", response_model=ConfigComparisonResponse)
async def compare_configs_endpoint(
    pipeline_config_ids: list[int] = Query(
        ...,
        description="Repeat param: pipeline_config_ids=1&pipeline_config_ids=2",
        min_length=1,
    ),
    evaluator_type: Literal["heuristic", "llm", "both"] = Query(
        "both",
        description="When `both`, response uses `buckets.heuristic` / `buckets.llm`.",
    ),
    dataset_id: int | None = Query(
        None,
        ge=1,
        description="Restrict to runs whose query case belongs to this dataset (same queries/corpus slice).",
    ),
    min_traced_runs: int | None = Query(
        None,
        ge=1,
        description="Require at least this many traced runs per pipeline_config_id in each computed bucket.",
    ),
    strict_comparison: bool = Query(
        False,
        description="Requires dataset_id; enforces identical query_case_id coverage across configs and min 2 runs per config (or higher if min_traced_runs is set).",
    ),
    include_benchmark_realism: bool = Query(
        False,
        description="Include runs tagged with benchmark_realism metadata (normally excluded from analytics).",
    ),
    db: AsyncSession = Depends(get_db),
) -> ConfigComparisonResponse:
    """Aggregate traced-run metrics per pipeline config (no SQL required by clients)."""
    try:
        return await compare_pipeline_configs(
            db,
            pipeline_config_ids,
            evaluator_type=evaluator_type,
            dataset_id=dataset_id,
            min_traced_runs=min_traced_runs,
            strict_comparison=strict_comparison,
            include_benchmark_realism=include_benchmark_realism,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("", response_model=RunListResponse)
async def list_runs_endpoint(
    dataset_id: int | None = Query(None),
    pipeline_config_id: int | None = Query(None),
    evaluator_type: Literal["heuristic", "llm"] | None = Query(None),
    status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> RunListResponse:
    """List runs newest-first with optional filters and pagination."""
    items, total = await list_runs(
        db,
        dataset_id=dataset_id,
        pipeline_config_id=pipeline_config_id,
        evaluator_type=evaluator_type,
        status=status,
        limit=limit,
        offset=offset,
    )
    return RunListResponse(items=items, total=total, limit=limit, offset=offset)



@router.post(
    "",
    response_model=RunCreateResponse,
    responses={
        201: {"description": "Heuristic run finished inline."},
        202: {"description": "Full run accepted; job enqueued for worker."},
    },
)
async def create_run_endpoint(
    body: RunCreateRequest,
    db: AsyncSession = Depends(get_db),
) -> RunCreateResponse | JSONResponse:
    """Create a run: heuristic finishes inline (201); full returns 202 and enqueues an RQ job."""
    try:
        await validate_run_create_prerequisites(
            db,
            query_case_id=body.query_case_id,
            pipeline_config_id=body.pipeline_config_id,
            document_id=body.document_id,
            eval_mode=body.eval_mode,
        )
    except QueryCaseNotFoundError:
        raise HTTPException(status_code=404, detail="Query case not found.") from None
    except PipelineConfigNotFoundError:
        raise HTTPException(status_code=404, detail="Pipeline config not found.") from None
    except DocumentNotFoundError:
        raise HTTPException(status_code=404, detail="Document not found.") from None
    except FullModeNotConfiguredError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e

    if body.eval_mode == "full":
        run = await tp.create_run(
            db,
            query_case_id=body.query_case_id,
            pipeline_config_id=body.pipeline_config_id,
            status=STATUS_RUNNING,
        )
        await db.commit()
        await db.refresh(run)
        try:
            job_id = enqueue_full_benchmark_run(run.id, body.document_id)
        except RedisError as e:
            raise HTTPException(
                status_code=503,
                detail=(
                    "Job queue unavailable (Redis). Start Redis and an RQ worker "
                    "(queue `contextlens_full_run`; see backend README)."
                ),
            ) from e
        payload = RunCreateResponse(
            run_id=run.id,
            status=run.status,
            eval_mode=body.eval_mode,
            job_id=job_id,
        )
        return JSONResponse(status_code=202, content=payload.model_dump(mode="json"))

    try:
        run = await create_and_execute_run_from_ids(
            db,
            query_case_id=body.query_case_id,
            pipeline_config_id=body.pipeline_config_id,
            document_id=body.document_id,
        )
    except anthropic.APIError as e:
        msg = getattr(e, "message", None) or str(e)
        raise HTTPException(status_code=502, detail=f"Anthropic API error: {msg}") from e
    except OpenAIAPIError as e:
        msg = getattr(e, "message", None) or str(e)
        raise HTTPException(status_code=502, detail=f"OpenAI API error: {msg}") from e

    payload = RunCreateResponse(run_id=run.id, status=run.status, eval_mode=body.eval_mode)
    return JSONResponse(
        status_code=201,
        content=payload.model_dump(mode="json", exclude_none=True),
    )


@router.post(
    "/{run_id:int}/requeue",
    response_model=RunRequeueResponse,
    status_code=202,
    summary="Re-enqueue a stuck full benchmark run",
)
async def requeue_full_run_endpoint(
    run_id: int,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Push another RQ job for an existing full-mode run (same worker pipeline as ``POST /runs``).

    **202** with a new ``job_id`` when accepted. **404** if the run does not exist. **409** if the
    run is not eligible (completed, heuristic-only, disallowed status, or worker lock held).
    **503** if Redis/RQ is unavailable or the active LLM provider API key is not configured.
    """
    try:
        run, job_id = await requeue_full_run(db, run_id)
    except RunNotFoundError:
        raise HTTPException(status_code=404, detail="Run not found.") from None
    except RunRequeueConflictError as exc:
        raise HTTPException(status_code=409, detail=exc.detail) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc
    except RedisError as exc:
        raise HTTPException(
            status_code=503,
            detail="Job queue unavailable (Redis). See backend README and docs/DEV_FULL_RUN_QUEUE.md.",
        ) from exc

    payload = RunRequeueResponse(run_id=run.id, status=run.status, job_id=job_id)
    return JSONResponse(status_code=202, content=payload.model_dump(mode="json"))


@router.get(
    "/{run_id:int}/queue-status",
    response_model=RunQueueStatusResponse,
    summary="Inspect full-run queue state (RQ job + lock)",
)
async def get_run_queue_status_endpoint(
    run_id: int,
    db: AsyncSession = Depends(get_db),
) -> RunQueueStatusResponse:
    """Best-effort inspection of Redis lock + RQ jobs for **full** benchmark runs.

    **Heuristic** runs return ``pipeline=heuristic`` with no Redis/RQ calls (``lock_present=false``,
    ``job_id`` null). **Full** runs require Redis; **503** if Redis is unavailable.

    ``job_id`` is **not** stored on the run row — this endpoint scans RQ registries for jobs
    whose first argument is ``run_id``. Completed jobs may disappear after TTL.

    ``requeue_eligible`` matches structural rules + lock (same as ``POST /requeue`` except it
    does **not** check the LLM API key or enqueue Redis).
    """
    try:
        return await get_run_queue_status(db, run_id)
    except RunNotFoundError:
        raise HTTPException(status_code=404, detail="Run not found.") from None
    except RedisError as exc:
        raise HTTPException(
            status_code=503,
            detail="Redis unavailable; cannot inspect queue or lock (see docs/DEV_FULL_RUN_QUEUE.md).",
        ) from exc


@router.get("/{run_id:int}", response_model=RunDetailResponse)
async def get_run_detail_endpoint(
    run_id: int,
    db: AsyncSession = Depends(get_db),
) -> RunDetailResponse:
    """Return query, config, retrieval hits, optional generation, evaluation, timings, evaluator type."""
    detail = await get_run_detail(db, run_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Run not found.")
    return detail
