"""Ingest plain text as a processed document (parse → chunk → embed → persist).

Shared logic for API uploads and offline benchmark scripts. Callers own high-level
error policy; on failure this module sets ``document.status`` to ``failed`` when
a row was already flushed.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Chunk, Document
from app.services.chunker import ChunkStrategy, chunk_text
from app.services.embedder import embed_texts
from app.services.parser import parse_document


def _ensure_upload_dir() -> Path:
    path = Path(settings.upload_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


async def ingest_text_file(
    session: AsyncSession,
    *,
    file_path: Path,
    title: str,
    source_type: str = "txt",
    chunk_strategy: ChunkStrategy = ChunkStrategy.FIXED,
    chunk_size: int = 512,
    chunk_overlap: int = 0,
    metadata_json: dict | None = None,
    commit: bool = True,
) -> Document:
    """Parse *file_path*, chunk, embed, insert chunks; set document ``processed``.

    Raises ``ValueError`` on limit violations or empty text (document row may be
    marked ``failed`` and committed when ``commit`` is True).
    """
    if chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be strictly less than chunk_size.")

    doc = Document(
        title=title,
        source_type=source_type,
        file_path=str(file_path),
        status="processing",
        metadata_json=metadata_json,
    )
    session.add(doc)
    await session.flush()

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
        if len(embeddings) != len(chunk_data_list):
            raise RuntimeError("Embedding batch size does not match chunk count.")
    except ValueError:
        doc.status = "failed"
        if commit:
            await session.commit()
        file_path.unlink(missing_ok=True)
        raise
    except Exception:
        doc.status = "failed"
        if commit:
            await session.commit()
        file_path.unlink(missing_ok=True)
        raise

    for cd, vec in zip(chunk_data_list, embeddings):
        session.add(
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
    await session.flush()
    if commit:
        await session.commit()
        await session.refresh(doc)
    return doc


async def ingest_plain_text(
    session: AsyncSession,
    *,
    title: str,
    text: str,
    chunk_strategy: ChunkStrategy = ChunkStrategy.FIXED,
    chunk_size: int = 512,
    chunk_overlap: int = 0,
    metadata_json: dict | None = None,
    commit: bool = True,
) -> Document:
    """Write *text* to a temp ``.txt`` under ``upload_dir`` and ingest it."""
    upload_dir = _ensure_upload_dir()
    dest = upload_dir / f"{uuid.uuid4().hex}.txt"
    dest.write_text(text.strip() + ("\n" if text.strip() else ""), encoding="utf-8")
    return await ingest_text_file(
        session,
        file_path=dest,
        title=title,
        source_type="txt",
        chunk_strategy=chunk_strategy,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        metadata_json=metadata_json,
        commit=commit,
    )
