"""Retrieval request and response schemas."""

from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    top_k: int = Field(5, ge=1, le=100)
    document_id: int | None = Field(
        None, description="Optional filter to a single document."
    )


class SearchResultItem(BaseModel):
    chunk_id: int
    document_id: int
    content: str
    chunk_index: int
    start_char: int
    end_char: int
    score: float = Field(
        ...,
        description=(
            "Cosine similarity between query and chunk embedding. "
            "Range: 1.0 = identical, 0.0 = orthogonal, negative = opposing."
        ),
    )


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResultItem]
