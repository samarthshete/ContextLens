"""Document schemas."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict


class DocumentStatus(str, Enum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    source_type: str
    status: DocumentStatus
    metadata_json: dict | None = None
    created_at: datetime


class DocumentListResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    source_type: str
    status: DocumentStatus
    created_at: datetime