"""Embedding service using sentence-transformers.

Loads the model once on first use and caches it for the process lifetime.
all-MiniLM-L6-v2 produces 384-dimensional float32 vectors.
"""

from functools import lru_cache

from sentence_transformers import SentenceTransformer

from app.config import settings


@lru_cache(maxsize=1)
def _get_model() -> SentenceTransformer:
    """Load and cache the sentence-transformer model."""
    return SentenceTransformer(settings.embedding_model_name)


def embed_text(text: str) -> list[float]:
    """Embed a single text string. Returns a list of floats (384-d)."""
    model = _get_model()
    vector = model.encode(text, normalize_embeddings=True)
    return vector.tolist()


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts. Returns a list of float lists (each 384-d)."""
    if not texts:
        return []
    model = _get_model()
    vectors = model.encode(texts, normalize_embeddings=True, batch_size=64)
    return vectors.tolist()
