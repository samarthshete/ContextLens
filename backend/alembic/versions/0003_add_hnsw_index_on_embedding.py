"""Add HNSW index for cosine similarity search on chunks.embedding.

Revision ID: 0003
Revises: 0002
Create Date: 2026-03-19

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # HNSW index for approximate nearest-neighbor cosine search.
    # vector_cosine_ops matches the <=> (cosine distance) operator.
    # m=16, ef_construction=64 are safe defaults; tune once data grows.
    op.create_index(
        "idx_chunks_embedding_cosine",
        "chunks",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )


def downgrade() -> None:
    op.drop_index("idx_chunks_embedding_cosine", table_name="chunks")
