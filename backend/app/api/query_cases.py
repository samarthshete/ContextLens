"""Benchmark query cases (read + create/update)."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.query_case_read import QueryCaseRead
from app.schemas.query_case_write import QueryCaseCreateRequest, QueryCaseUpdateRequest
from app.services.query_case_list import (
    DatasetNotFoundForFilterError,
    get_query_case_by_id,
    list_query_cases,
)
from app.services.query_case_delete import QueryCaseDeleteConflictError, delete_query_case
from app.services.query_case_write import (
    DatasetNotFoundForQueryCaseError,
    create_query_case,
    update_query_case,
)

router = APIRouter()


@router.get("", response_model=list[QueryCaseRead])
async def list_query_cases_endpoint(
    dataset_id: int | None = Query(None, description="Filter to query cases in this dataset."),
    db: AsyncSession = Depends(get_db),
) -> list[QueryCaseRead]:
    try:
        rows = await list_query_cases(db, dataset_id=dataset_id)
    except DatasetNotFoundForFilterError:
        raise HTTPException(status_code=404, detail="Dataset not found.") from None
    return [QueryCaseRead.model_validate(r) for r in rows]


@router.post("", response_model=QueryCaseRead, status_code=201)
async def create_query_case_endpoint(
    body: QueryCaseCreateRequest,
    db: AsyncSession = Depends(get_db),
) -> QueryCaseRead:
    try:
        row = await create_query_case(
            db,
            dataset_id=body.dataset_id,
            query_text=body.query_text,
            expected_answer=body.expected_answer,
            metadata_json=body.metadata_json,
        )
    except DatasetNotFoundForQueryCaseError:
        raise HTTPException(status_code=404, detail="Dataset not found.") from None
    return QueryCaseRead.model_validate(row)


@router.get("/{query_case_id}", response_model=QueryCaseRead)
async def get_query_case_endpoint(
    query_case_id: int,
    db: AsyncSession = Depends(get_db),
) -> QueryCaseRead:
    row = await get_query_case_by_id(db, query_case_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Query case not found.")
    return QueryCaseRead.model_validate(row)


@router.patch("/{query_case_id}", response_model=QueryCaseRead)
async def patch_query_case_endpoint(
    query_case_id: int,
    body: QueryCaseUpdateRequest,
    db: AsyncSession = Depends(get_db),
) -> QueryCaseRead:
    fs = frozenset(body.model_fields_set)
    try:
        row = await update_query_case(
            db,
            query_case_id,
            dataset_id=body.dataset_id if "dataset_id" in fs else None,
            query_text=body.query_text if "query_text" in fs else None,
            expected_answer=body.expected_answer if "expected_answer" in fs else None,
            metadata_json=body.metadata_json if "metadata_json" in fs else None,
            fields_set=fs,
        )
    except DatasetNotFoundForQueryCaseError:
        raise HTTPException(status_code=404, detail="Dataset not found.") from None
    if row is None:
        raise HTTPException(status_code=404, detail="Query case not found.")
    return QueryCaseRead.model_validate(row)


@router.delete("/{query_case_id}", status_code=204)
async def delete_query_case_endpoint(
    query_case_id: int,
    db: AsyncSession = Depends(get_db),
) -> None:
    try:
        deleted = await delete_query_case(db, query_case_id)
    except QueryCaseDeleteConflictError as exc:
        raise HTTPException(status_code=409, detail=exc.detail) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="Query case not found.")
