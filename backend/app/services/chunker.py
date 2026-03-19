"""Text chunking helpers."""

from dataclasses import dataclass
from enum import Enum


class ChunkStrategy(str, Enum):
    FIXED = "fixed"
    RECURSIVE = "recursive"


@dataclass(slots=True)
class ChunkData:
    content: str
    chunk_index: int
    start_char: int
    end_char: int
    metadata_json: dict | None = None


def chunk_text(
    text: str,
    strategy: ChunkStrategy,
    chunk_size: int = 512,
    overlap: int = 0,
) -> list[ChunkData]:
    """Split text into ordered chunks with source offsets."""
    cleaned_text = _normalize_text(text)
    if not cleaned_text:
        return []

    _validate_chunk_params(chunk_size, overlap)

    if strategy == ChunkStrategy.FIXED:
        return _chunk_fixed(cleaned_text, chunk_size, overlap)

    if strategy == ChunkStrategy.RECURSIVE:
        return _chunk_recursive(cleaned_text, chunk_size, overlap)

    raise ValueError(f"Unknown strategy: {strategy}")


def _validate_chunk_params(chunk_size: int, overlap: int) -> None:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than 0")
    if overlap < 0:
        raise ValueError("overlap must be 0 or greater")
    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size")


def _normalize_text(text: str) -> str:
    return text.strip()


def _chunk_fixed(text: str, chunk_size: int, overlap: int) -> list[ChunkData]:
    chunks: list[ChunkData] = []
    step = chunk_size - overlap
    chunk_index = 0

    for start in range(0, len(text), step):
        end = min(start + chunk_size, len(text))
        chunk_text_value = text[start:end].strip()

        if not chunk_text_value:
            continue

        chunks.append(
            ChunkData(
                content=chunk_text_value,
                chunk_index=chunk_index,
                start_char=start,
                end_char=end,
                metadata_json={
                    "strategy": ChunkStrategy.FIXED.value,
                    "chunk_size": chunk_size,
                    "overlap": overlap,
                },
            )
        )
        chunk_index += 1

        if end >= len(text):
            break

    return chunks


def _chunk_recursive(text: str, chunk_size: int, overlap: int) -> list[ChunkData]:
    separators = ["\n\n", "\n", ". ", " ", ""]
    pieces = _split_recursive(text, chunk_size, separators)
    return _build_chunks_from_pieces(
        full_text=text,
        pieces=pieces,
        strategy=ChunkStrategy.RECURSIVE,
        chunk_size=chunk_size,
        overlap=overlap,
    )


def _split_recursive(text: str, chunk_size: int, separators: list[str]) -> list[str]:
    if len(text) <= chunk_size:
        return [text.strip()] if text.strip() else []

    separator = separators[0]

    if separator == "":
        return [
            text[i : i + chunk_size].strip()
            for i in range(0, len(text), chunk_size)
            if text[i : i + chunk_size].strip()
        ]

    parts = text.split(separator)
    chunks: list[str] = []
    current = ""

    for index, part in enumerate(parts):
        suffix = separator if index < len(parts) - 1 and separator not in {" ", ""} else ""
        candidate = f"{current}{part}{suffix}" if current else f"{part}{suffix}"

        if len(candidate) <= chunk_size:
            current = candidate
            continue

        if current.strip():
            chunks.append(current.strip())

        if len(part) > chunk_size and len(separators) > 1:
            chunks.extend(_split_recursive(part, chunk_size, separators[1:]))
            current = ""
        else:
            current = f"{part}{suffix}"

    if current.strip():
        chunks.append(current.strip())

    return chunks


def _build_chunks_from_pieces(
    full_text: str,
    pieces: list[str],
    strategy: ChunkStrategy,
    chunk_size: int,
    overlap: int,
) -> list[ChunkData]:
    chunks: list[ChunkData] = []
    search_start = 0

    for chunk_index, piece in enumerate(pieces):
        content = piece.strip()
        if not content:
            continue

        start = full_text.find(content, search_start)
        if start == -1:
            start = full_text.find(content)

        if start == -1:
            raise ValueError("Failed to map chunk back to source text.")

        end = start + len(content)
        search_start = end

        chunks.append(
            ChunkData(
                content=content,
                chunk_index=chunk_index,
                start_char=start,
                end_char=end,
                metadata_json={
                    "strategy": strategy.value,
                    "chunk_size": chunk_size,
                    "overlap": overlap,
                },
            )
        )

    return chunks