"""Chunk schemas."""

from pydantic import BaseModel, ConfigDict


class ChunkResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    document_id: int
    content: str
    chunk_index: int
    start_char: int | None = None
    end_char: int | None = None
    metadata_json: dict | None = None