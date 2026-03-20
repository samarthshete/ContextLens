"""Runs API: create (inline heuristic or async full benchmark), list, config comparison, detail."""

from typing import Literal

import anthropic
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.queue.full_run import enqueue_full_benchmark_run
from app.schemas.config_comparison import ConfigComparisonResponse
from app.schemas.run_create import RunCreateRequest, RunCreateResponse
from app.schemas.run_detail import RunDetailResponse
from app.schemas.run_list import RunListResponse
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
from app.services.run_list import list_runs

router = APIRouter()


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
    combine_evaluators: bool = Query(
        False,
        description="If true, merge heuristic + LLM into one row per config (`evaluator_type=combined`).",
    ),
    db: AsyncSession = Depends(get_db),
) -> ConfigComparisonResponse:
    """Aggregate traced-run metrics per pipeline config (no SQL required by clients)."""
    try:
        return await compare_pipeline_configs(
            db,
            pipeline_config_ids,
            combine_evaluators=combine_evaluators,
            evaluator_type=evaluator_type,
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

    payload = RunCreateResponse(run_id=run.id, status=run.status, eval_mode=body.eval_mode)
    return JSONResponse(
        status_code=201,
        content=payload.model_dump(mode="json", exclude_none=True),
    )


@router.get("/{run_id}", response_model=RunDetailResponse)
async def get_run_detail_endpoint(
    run_id: int,
    db: AsyncSession = Depends(get_db),
) -> RunDetailResponse:
    """Return query, config, retrieval hits, optional generation, evaluation, timings, evaluator type."""
    detail = await get_run_detail(db, run_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Run not found.")
    return detail
