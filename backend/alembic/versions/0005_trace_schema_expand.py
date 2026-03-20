"""Expand trace/benchmark schema: descriptions, query_text, pipeline columns, timestamps.

Revision ID: 0005
Revises: 0004
Create Date: 2026-03-20

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("datasets", sa.Column("description", sa.Text(), nullable=True))

    op.execute(sa.text('ALTER TABLE query_cases RENAME COLUMN "query" TO query_text'))
    op.add_column(
        "query_cases",
        sa.Column("expected_answer", sa.Text(), nullable=True),
    )

    op.add_column(
        "pipeline_configs",
        sa.Column("embedding_model", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "pipeline_configs",
        sa.Column("chunk_strategy", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "pipeline_configs",
        sa.Column("chunk_size", sa.Integer(), nullable=True),
    )
    op.add_column(
        "pipeline_configs",
        sa.Column("chunk_overlap", sa.Integer(), nullable=True),
    )
    op.add_column(
        "pipeline_configs",
        sa.Column("top_k", sa.Integer(), nullable=True),
    )

    op.execute(
        sa.text("UPDATE pipeline_configs SET name = 'legacy' WHERE name IS NULL")
    )
    op.execute(
        sa.text(
            "UPDATE pipeline_configs SET embedding_model = 'all-MiniLM-L6-v2' "
            "WHERE embedding_model IS NULL"
        )
    )
    op.execute(
        sa.text(
            "UPDATE pipeline_configs SET chunk_strategy = 'fixed' "
            "WHERE chunk_strategy IS NULL"
        )
    )
    op.execute(
        sa.text("UPDATE pipeline_configs SET chunk_size = 512 WHERE chunk_size IS NULL")
    )
    op.execute(
        sa.text(
            "UPDATE pipeline_configs SET chunk_overlap = 0 WHERE chunk_overlap IS NULL"
        )
    )
    op.execute(sa.text("UPDATE pipeline_configs SET top_k = 5 WHERE top_k IS NULL"))

    op.alter_column(
        "pipeline_configs",
        "name",
        existing_type=sa.String(length=256),
        nullable=False,
    )
    op.alter_column(
        "pipeline_configs",
        "embedding_model",
        existing_type=sa.String(length=128),
        nullable=False,
    )
    op.alter_column(
        "pipeline_configs",
        "chunk_strategy",
        existing_type=sa.String(length=32),
        nullable=False,
    )
    op.alter_column(
        "pipeline_configs",
        "chunk_size",
        existing_type=sa.Integer(),
        nullable=False,
    )
    op.alter_column(
        "pipeline_configs",
        "chunk_overlap",
        existing_type=sa.Integer(),
        nullable=False,
    )
    op.alter_column(
        "pipeline_configs",
        "top_k",
        existing_type=sa.Integer(),
        nullable=False,
    )

    op.add_column(
        "retrieval_results",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_retrieval_results_run_id_rank",
        "retrieval_results",
        ["run_id", "rank"],
        unique=False,
    )

    op.add_column(
        "evaluation_results",
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("evaluation_results", "metadata_json")

    op.drop_index("ix_retrieval_results_run_id_rank", table_name="retrieval_results")
    op.drop_column("retrieval_results", "created_at")

    op.alter_column("pipeline_configs", "top_k", nullable=True)
    op.alter_column("pipeline_configs", "chunk_overlap", nullable=True)
    op.alter_column("pipeline_configs", "chunk_size", nullable=True)
    op.alter_column("pipeline_configs", "chunk_strategy", nullable=True)
    op.alter_column("pipeline_configs", "embedding_model", nullable=True)
    op.alter_column("pipeline_configs", "name", nullable=True)

    op.drop_column("pipeline_configs", "top_k")
    op.drop_column("pipeline_configs", "chunk_overlap")
    op.drop_column("pipeline_configs", "chunk_size")
    op.drop_column("pipeline_configs", "chunk_strategy")
    op.drop_column("pipeline_configs", "embedding_model")

    op.drop_column("query_cases", "expected_answer")
    op.execute(sa.text('ALTER TABLE query_cases RENAME COLUMN query_text TO "query"'))

    op.drop_column("datasets", "description")
