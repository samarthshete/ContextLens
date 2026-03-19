"""Add pgvector extension and embedding column to chunks.

Revision ID: 0002
Revises: 0001
Create Date: 2026-03-19

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# all-MiniLM-L6-v2 → 384 dimensions
EMBEDDING_DIM = 384


def upgrade() -> None:
    # Enable the pgvector extension (idempotent).
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # Add nullable embedding column.
    op.add_column(
        "chunks",
        sa.Column("embedding", Vector(EMBEDDING_DIM), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("chunks", "embedding")
    # Don't drop the extension — other tables may use it.
