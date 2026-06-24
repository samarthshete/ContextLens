"""Embedding service using the OpenAI embeddings API.

Uses ``text-embedding-3-small`` with ``dimensions=384`` so the output matches the
existing pgvector column (``EMBEDDING_DIM = 384`` in ``app/models/chunk.py`` and
migration ``0002``) — no schema/migration change required.

This replaces the previous local ``sentence-transformers`` model so the service
runs without PyTorch, keeping memory low enough for small (e.g. 512 MB) hosts.
OpenAI embeddings are unit-normalized and the index uses cosine similarity, so
no extra normalization is needed.
"""

from functools import lru_cache

from openai import OpenAI

from app.config import settings

# Must match the pgvector column dimension (see app/models/chunk.py).
EMBEDDING_DIM = 384

# Legacy local model names that can no longer be served at runtime; map to the
# OpenAI small embedding model when encountered.
_LEGACY_LOCAL_PREFIXES = ("all-", "sentence-transformers/")


@lru_cache(maxsize=1)
def _client() -> OpenAI:
    """Lazily build a synchronous OpenAI client (keeps embed_* sync)."""
    key = (settings.openai_api_key or "").strip()
    if not key:
        raise RuntimeError(
            "openai_api_key / OPENAI_API_KEY is not set. Required for embeddings."
        )
    return OpenAI(api_key=key)


def _model_name() -> str:
    name = (settings.embedding_model_name or "").strip()
    if not name or name.startswith(_LEGACY_LOCAL_PREFIXES) or "MiniLM" in name:
        return "text-embedding-3-small"
    return name


def embed_text(text: str) -> list[float]:
    """Embed a single text string. Returns a 384-dimensional list of floats."""
    resp = _client().embeddings.create(
        model=_model_name(), input=text, dimensions=EMBEDDING_DIM
    )
    return list(resp.data[0].embedding)


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts. Returns a list of 384-dimensional float lists."""
    if not texts:
        return []
    resp = _client().embeddings.create(
        model=_model_name(), input=texts, dimensions=EMBEDDING_DIM
    )
    # The API may return items out of order; sort by index to match `texts`.
    ordered = sorted(resp.data, key=lambda d: d.index)
    return [list(item.embedding) for item in ordered]
