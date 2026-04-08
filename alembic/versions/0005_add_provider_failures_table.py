"""Add provider failures table.

Revision ID: 0005_add_provider_failures_table
Revises: 0004_add_source_query_traceability
Create Date: 2026-04-08 20:05:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0005_add_provider_failures_table"
down_revision = "0004_add_source_query_traceability"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "provider_failures",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("provider_name", sa.String(length=100), nullable=False),
        sa.Column("query_text", sa.String(length=255), nullable=False),
        sa.Column("query_kind", sa.String(length=50), nullable=True),
        sa.Column("error_type", sa.String(length=100), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("retryable", sa.Boolean(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["research_runs.id"], name=op.f("fk_provider_failures_run_id_research_runs"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_provider_failures")),
    )
    op.create_index(op.f("ix_provider_failures_created_at"), "provider_failures", ["created_at"], unique=False)
    op.create_index(op.f("ix_provider_failures_occurred_at"), "provider_failures", ["occurred_at"], unique=False)
    op.create_index(op.f("ix_provider_failures_provider_name"), "provider_failures", ["provider_name"], unique=False)
    op.create_index(op.f("ix_provider_failures_run_id"), "provider_failures", ["run_id"], unique=False)
    op.create_index("ix_provider_failures_run_id_occurred_at", "provider_failures", ["run_id", "occurred_at"], unique=False)
    op.create_index("ix_provider_failures_run_id_provider_name", "provider_failures", ["run_id", "provider_name"], unique=False)
    op.create_index("ix_provider_failures_run_id_retryable", "provider_failures", ["run_id", "retryable"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_provider_failures_run_id_retryable", table_name="provider_failures")
    op.drop_index("ix_provider_failures_run_id_provider_name", table_name="provider_failures")
    op.drop_index("ix_provider_failures_run_id_occurred_at", table_name="provider_failures")
    op.drop_index(op.f("ix_provider_failures_run_id"), table_name="provider_failures")
    op.drop_index(op.f("ix_provider_failures_provider_name"), table_name="provider_failures")
    op.drop_index(op.f("ix_provider_failures_occurred_at"), table_name="provider_failures")
    op.drop_index(op.f("ix_provider_failures_created_at"), table_name="provider_failures")
    op.drop_table("provider_failures")
