"""Metrics-ready schema: datasets, query_cases, pipeline_configs, runs, retrieval_results, evaluation_results.

Revision ID: 0004
Revises: 0003
Create Date: 2026-03-19

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "datasets",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "pipeline_configs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=256), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "query_cases",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("dataset_id", sa.Integer(), nullable=False),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["dataset_id"], ["datasets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_query_cases_dataset_id", "query_cases", ["dataset_id"])

    op.create_table(
        "runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("query_case_id", sa.Integer(), nullable=False),
        sa.Column("pipeline_config_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("retrieval_latency_ms", sa.Integer(), nullable=True),
        sa.Column("generation_latency_ms", sa.Integer(), nullable=True),
        sa.Column("evaluation_latency_ms", sa.Integer(), nullable=True),
        sa.Column("total_latency_ms", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["query_case_id"], ["query_cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["pipeline_config_id"], ["pipeline_configs.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_runs_query_case_id", "runs", ["query_case_id"])
    op.create_index("ix_runs_pipeline_config_id", "runs", ["pipeline_config_id"])

    op.create_table(
        "retrieval_results",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("chunk_id", sa.Integer(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(["chunk_id"], ["chunks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_retrieval_results_run_id", "retrieval_results", ["run_id"])
    op.create_index("ix_retrieval_results_chunk_id", "retrieval_results", ["chunk_id"])

    op.create_table(
        "evaluation_results",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("faithfulness", sa.Float(), nullable=True),
        sa.Column("completeness", sa.Float(), nullable=True),
        sa.Column("retrieval_relevance", sa.Float(), nullable=True),
        sa.Column("context_coverage", sa.Float(), nullable=True),
        sa.Column("failure_type", sa.String(length=64), nullable=True),
        sa.Column("used_llm_judge", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("cost_usd", sa.Numeric(14, 6), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", name="uq_evaluation_results_run_id"),
    )
    op.create_index("ix_evaluation_results_run_id", "evaluation_results", ["run_id"])


def downgrade() -> None:
    op.drop_index("ix_evaluation_results_run_id", table_name="evaluation_results")
    op.drop_table("evaluation_results")
    op.drop_index("ix_retrieval_results_chunk_id", table_name="retrieval_results")
    op.drop_index("ix_retrieval_results_run_id", table_name="retrieval_results")
    op.drop_table("retrieval_results")
    op.drop_index("ix_runs_pipeline_config_id", table_name="runs")
    op.drop_index("ix_runs_query_case_id", table_name="runs")
    op.drop_table("runs")
    op.drop_index("ix_query_cases_dataset_id", table_name="query_cases")
    op.drop_table("query_cases")
    op.drop_table("pipeline_configs")
    op.drop_table("datasets")
