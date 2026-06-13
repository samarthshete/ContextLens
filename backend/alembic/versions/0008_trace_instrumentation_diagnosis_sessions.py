"""Add runs.trace_instrumentation_json and diagnosis_timing_sessions."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0008_trace_instr_diag"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "runs",
        sa.Column("trace_instrumentation_json", JSONB, nullable=True),
    )
    op.create_table(
        "diagnosis_timing_sessions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("first_meaningful_insight_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution_label", sa.String(length=128), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("session_key", sa.String(length=256), nullable=True),
        sa.Column("synthetic", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_diagnosis_timing_sessions_run_id",
        "diagnosis_timing_sessions",
        ["run_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_diagnosis_timing_sessions_run_id", table_name="diagnosis_timing_sessions")
    op.drop_table("diagnosis_timing_sessions")
    op.drop_column("runs", "trace_instrumentation_json")
