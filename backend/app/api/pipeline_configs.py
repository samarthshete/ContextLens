"""Pipeline configs for benchmark runs (read + create/update)."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.pipeline_config_read import PipelineConfigRead
from app.schemas.pipeline_config_write import PipelineConfigCreateRequest, PipelineConfigUpdateRequest
from app.services.pipeline_config_delete import (
    PipelineConfigDeleteConflictError,
    delete_pipeline_config,
)
from app.services.pipeline_config_list import get_pipeline_config_by_id, list_pipeline_configs
from app.services.pipeline_config_write import (
    InvalidPipelineConfigError,
    create_pipeline_config,
    update_pipeline_config,
)

router = APIRouter()


@router.get("", response_model=list[PipelineConfigRead])
async def list_pipeline_configs_endpoint(
    db: AsyncSession = Depends(get_db),
) -> list[PipelineConfigRead]:
    rows = await list_pipeline_configs(db)
    return [PipelineConfigRead.model_validate(r) for r in rows]


@router.post("", response_model=PipelineConfigRead, status_code=201)
async def create_pipeline_config_endpoint(
    body: PipelineConfigCreateRequest,
    db: AsyncSession = Depends(get_db),
) -> PipelineConfigRead:
    try:
        row = await create_pipeline_config(
            db,
            name=body.name,
            embedding_model=body.embedding_model,
            chunk_strategy=body.chunk_strategy,
            chunk_size=body.chunk_size,
            chunk_overlap=body.chunk_overlap,
            top_k=body.top_k,
            metadata_json=body.metadata_json,
        )
    except InvalidPipelineConfigError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return PipelineConfigRead.model_validate(row)


@router.get("/{pipeline_config_id}", response_model=PipelineConfigRead)
async def get_pipeline_config_endpoint(
    pipeline_config_id: int,
    db: AsyncSession = Depends(get_db),
) -> PipelineConfigRead:
    row = await get_pipeline_config_by_id(db, pipeline_config_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Pipeline config not found.")
    return PipelineConfigRead.model_validate(row)


@router.patch("/{pipeline_config_id}", response_model=PipelineConfigRead)
async def patch_pipeline_config_endpoint(
    pipeline_config_id: int,
    body: PipelineConfigUpdateRequest,
    db: AsyncSession = Depends(get_db),
) -> PipelineConfigRead:
    fs = frozenset(body.model_fields_set)
    try:
        row = await update_pipeline_config(
            db,
            pipeline_config_id,
            name=body.name if "name" in fs else None,
            embedding_model=body.embedding_model if "embedding_model" in fs else None,
            chunk_strategy=body.chunk_strategy if "chunk_strategy" in fs else None,
            chunk_size=body.chunk_size if "chunk_size" in fs else None,
            chunk_overlap=body.chunk_overlap if "chunk_overlap" in fs else None,
            top_k=body.top_k if "top_k" in fs else None,
            metadata_json=body.metadata_json if "metadata_json" in fs else None,
            fields_set=fs,
        )
    except InvalidPipelineConfigError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    if row is None:
        raise HTTPException(status_code=404, detail="Pipeline config not found.")
    return PipelineConfigRead.model_validate(row)


@router.delete("/{pipeline_config_id}", status_code=204)
async def delete_pipeline_config_endpoint(
    pipeline_config_id: int,
    db: AsyncSession = Depends(get_db),
) -> None:
    try:
        deleted = await delete_pipeline_config(db, pipeline_config_id)
    except PipelineConfigDeleteConflictError as exc:
        raise HTTPException(status_code=409, detail=exc.detail) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="Pipeline config not found.")
