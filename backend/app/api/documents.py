"""Document API endpoints."""

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models import Chunk, Document
from app.schemas.chunk import ChunkResponse
from app.schemas.document import DocumentListResponse, DocumentResponse
from app.services.chunker import ChunkStrategy, chunk_text
from app.services.embedder import embed_texts
from app.services.parser import parse_document

router = APIRouter()

ALLOWED_EXTENSIONS = {".pdf", ".txt", ".md", ".markdown"}


def _ensure_upload_dir() -> Path:
    """Ensure upload directory exists and return its path."""
    path = Path(settings.upload_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


async def _save_upload(file: UploadFile, upload_dir: Path) -> tuple[Path, str]:
    """Validate extension, read content, check size, save to disk.

    Returns (file_path, source_type).
    """
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Allowed: PDF, TXT, Markdown.",
        )

    raw_bytes = await file.read()
    if len(raw_bytes) > settings.max_upload_size_bytes:
        mb = settings.max_upload_size_bytes // (1024 * 1024)
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum allowed size is {mb} MB.",
        )

    dest = upload_dir / f"{uuid.uuid4().hex}{ext}"
    dest.write_bytes(raw_bytes)
    source_type = "md" if ext in (".md", ".markdown") else ext.lstrip(".")
    return dest, source_type


# ---------------------------------------------------------------------------
# Write endpoints — these call session.commit() explicitly.
# ---------------------------------------------------------------------------


@router.post("", response_model=DocumentResponse, status_code=201)
async def upload_document(
    file: UploadFile = File(...),
    chunk_strategy: ChunkStrategy = Query(ChunkStrategy.FIXED),
    chunk_size: int = Query(512, gt=0, le=100_000),
    chunk_overlap: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """Upload a document, parse it, chunk it, embed, and persist."""
    if chunk_overlap >= chunk_size:
        raise HTTPException(
            status_code=400,
            detail="chunk_overlap must be strictly less than chunk_size.",
        )

    upload_dir = _ensure_upload_dir()
    file_path, source_type = await _save_upload(file, upload_dir)

    title = file.filename or file_path.name

    # 1. Create document row with status="processing".
    doc = Document(
        title=title,
        source_type=source_type,
        file_path=str(file_path),
        status="processing",
        metadata_json={
            "chunk_strategy": chunk_strategy.value,
            "chunk_size": chunk_size,
            "chunk_overlap": chunk_overlap,
        },
    )
    db.add(doc)
    await db.flush()  # populate doc.id

    # 2. Parse, chunk, embed — all inside one try so we can mark "failed" atomically.
    try:
        raw_text = parse_document(file_path)

        if len(raw_text) > settings.max_text_length:
            raise ValueError(
                f"Extracted text is {len(raw_text)} chars, "
                f"exceeds limit of {settings.max_text_length}."
            )

        chunk_data_list = chunk_text(
            raw_text,
            strategy=chunk_strategy,
            chunk_size=chunk_size,
            overlap=chunk_overlap,
        )

        if len(chunk_data_list) > settings.max_chunks_per_document:
            raise ValueError(
                f"Document produces {len(chunk_data_list)} chunks, "
                f"exceeds limit of {settings.max_chunks_per_document}."
            )

        texts = [cd.content for cd in chunk_data_list]
        embeddings = embed_texts(texts)
    except ValueError as exc:
        # Limit violations — mark failed, commit just the status, return 422.
        doc.status = "failed"
        await db.commit()
        file_path.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        doc.status = "failed"
        await db.commit()
        file_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=422,
            detail="Failed to process document. The file may be corrupt or empty.",
        ) from exc

    # 3. Persist chunks + embeddings and mark "processed" in one commit.
    #    If this commit fails, *no* partial chunks are persisted.
    for cd, vec in zip(chunk_data_list, embeddings):
        db.add(
            Chunk(
                document_id=doc.id,
                content=cd.content,
                chunk_index=cd.chunk_index,
                start_char=cd.start_char,
                end_char=cd.end_char,
                metadata_json=cd.metadata_json,
                embedding=vec,
            )
        )

    doc.raw_text = raw_text
    doc.status = "processed"
    await db.commit()
    await db.refresh(doc)
    return doc


@router.delete("/{document_id}", status_code=204)
async def delete_document(document_id: int, db: AsyncSession = Depends(get_db)):
    """Delete a document, cascade-delete its chunks, remove the file."""
    result = await db.execute(
        select(Document).where(Document.id == document_id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")

    Path(doc.file_path).unlink(missing_ok=True)
    await db.delete(doc)
    await db.commit()


# ---------------------------------------------------------------------------
# Read endpoints — no commit needed.
# ---------------------------------------------------------------------------


@router.get("", response_model=list[DocumentListResponse])
async def list_documents(db: AsyncSession = Depends(get_db)):
    """List all documents, newest first."""
    result = await db.execute(
        select(Document).order_by(Document.created_at.desc())
    )
    return result.scalars().all()


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(document_id: int, db: AsyncSession = Depends(get_db)):
    """Fetch a single document by ID."""
    result = await db.execute(
        select(Document).where(Document.id == document_id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
    return doc


@router.get("/{document_id}/chunks", response_model=list[ChunkResponse])
async def get_document_chunks(
    document_id: int, db: AsyncSession = Depends(get_db)
):
    """Return all chunks for a document, ordered by chunk_index."""
    result = await db.execute(
        select(Document).where(Document.id == document_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Document not found.")

    result = await db.execute(
        select(Chunk)
        .where(Chunk.document_id == document_id)
        .order_by(Chunk.chunk_index)
    )
    return result.scalars().all()
