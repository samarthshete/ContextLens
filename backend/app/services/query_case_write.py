"""Create / update benchmark query cases."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Dataset, QueryCase


class DatasetNotFoundForQueryCaseError(LookupError):
    """``dataset_id`` does not reference an existing ``datasets`` row."""

    def __init__(self, dataset_id: int) -> None:
        self.dataset_id = dataset_id
        super().__init__(f"no dataset id={dataset_id}")


async def create_query_case(
    session: AsyncSession,
    *,
    dataset_id: int,
    query_text: str,
    expected_answer: str | None = None,
    metadata_json: dict[str, Any] | None = None,
) -> QueryCase:
    parent = await session.get(Dataset, dataset_id)
    if parent is None:
        raise DatasetNotFoundForQueryCaseError(dataset_id)

    row = QueryCase(
        dataset_id=dataset_id,
        query_text=query_text,
        expected_answer=expected_answer,
        metadata_json=metadata_json,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def update_query_case(
    session: AsyncSession,
    query_case_id: int,
    *,
    dataset_id: int | None = None,
    query_text: str | None = None,
    expected_answer: str | None = None,
    metadata_json: dict[str, Any] | None = None,
    fields_set: frozenset[str] | None = None,
) -> QueryCase | None:
    row = await session.get(QueryCase, query_case_id)
    if row is None:
        return None

    fs = fields_set or frozenset()

    if "dataset_id" in fs:
        assert dataset_id is not None
        parent = await session.get(Dataset, dataset_id)
        if parent is None:
            raise DatasetNotFoundForQueryCaseError(dataset_id)
        row.dataset_id = dataset_id

    if "query_text" in fs and query_text is not None:
        row.query_text = query_text
    if "expected_answer" in fs:
        row.expected_answer = expected_answer
    if "metadata_json" in fs:
        row.metadata_json = metadata_json

    await session.commit()
    await session.refresh(row)
    return row
