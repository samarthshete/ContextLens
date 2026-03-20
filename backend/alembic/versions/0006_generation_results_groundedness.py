"""generation_results table; evaluation_results.groundedness.

Revision ID: 0006
Revises: 0005
Create Date: 2026-03-20

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "generation_results",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("answer_text", sa.Text(), nullable=False),
        sa.Column("model_id", sa.String(length=128), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", name="uq_generation_results_run_id"),
    )
    op.create_index(
        "ix_generation_results_run_id", "generation_results", ["run_id"], unique=False
    )

    op.add_column(
        "evaluation_results",
        sa.Column("groundedness", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("evaluation_results", "groundedness")
    op.drop_index("ix_generation_results_run_id", table_name="generation_results")
    op.drop_table("generation_results")
