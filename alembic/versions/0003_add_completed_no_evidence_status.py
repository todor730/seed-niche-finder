"""Add completed_no_evidence research run status.

Revision ID: 0003_add_completed_no_evidence_status
Revises: 0002_add_evidence_layer
Create Date: 2026-04-08 18:05:00
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "0003_add_completed_no_evidence_status"
down_revision = "0002_add_evidence_layer"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute("ALTER TYPE research_run_status ADD VALUE IF NOT EXISTS 'completed_no_evidence'")


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute(
        """
        UPDATE research_runs
        SET status = 'completed'
        WHERE status = 'completed_no_evidence'
        """
    )
    op.execute("ALTER TYPE research_run_status RENAME TO research_run_status_old")
    op.execute(
        """
        CREATE TYPE research_run_status AS ENUM (
            'pending',
            'running',
            'completed',
            'failed',
            'cancelled'
        )
        """
    )
    op.execute(
        """
        ALTER TABLE research_runs
        ALTER COLUMN status
        TYPE research_run_status
        USING status::text::research_run_status
        """
    )
    op.execute("DROP TYPE research_run_status_old")
