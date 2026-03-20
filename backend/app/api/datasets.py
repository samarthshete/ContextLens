"""Benchmark datasets (registry discovery + writes)."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.dataset_read import DatasetRead
from app.schemas.dataset_write import DatasetCreateRequest, DatasetUpdateRequest
from app.services.dataset_delete import DatasetDeleteConflictError, delete_dataset
from app.services.dataset_list import get_dataset_by_id, list_datasets
from app.services.dataset_write import create_dataset, update_dataset

router = APIRouter()


@router.get("", response_model=list[DatasetRead])
async def list_datasets_endpoint(
    db: AsyncSession = Depends(get_db),
) -> list[DatasetRead]:
    rows = await list_datasets(db)
    return [DatasetRead.model_validate(r) for r in rows]


@router.post("", response_model=DatasetRead, status_code=201)
async def create_dataset_endpoint(
    body: DatasetCreateRequest,
    db: AsyncSession = Depends(get_db),
) -> DatasetRead:
    row = await create_dataset(
        db,
        name=body.name,
        description=body.description,
        metadata_json=body.metadata_json,
    )
    return DatasetRead.model_validate(row)


@router.get("/{dataset_id}", response_model=DatasetRead)
async def get_dataset_endpoint(
    dataset_id: int,
    db: AsyncSession = Depends(get_db),
) -> DatasetRead:
    row = await get_dataset_by_id(db, dataset_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Dataset not found.")
    return DatasetRead.model_validate(row)


@router.patch("/{dataset_id}", response_model=DatasetRead)
async def patch_dataset_endpoint(
    dataset_id: int,
    body: DatasetUpdateRequest,
    db: AsyncSession = Depends(get_db),
) -> DatasetRead:
    fs = frozenset(body.model_fields_set)
    row = await update_dataset(
        db,
        dataset_id,
        name=body.name if "name" in fs else None,
        description=body.description if "description" in fs else None,
        metadata_json=body.metadata_json if "metadata_json" in fs else None,
        fields_set=fs,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Dataset not found.")
    return DatasetRead.model_validate(row)


@router.delete("/{dataset_id}", status_code=204)
async def delete_dataset_endpoint(
    dataset_id: int,
    db: AsyncSession = Depends(get_db),
) -> None:
    try:
        deleted = await delete_dataset(db, dataset_id)
    except DatasetDeleteConflictError as exc:
        raise HTTPException(status_code=409, detail=exc.detail) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="Dataset not found.")
