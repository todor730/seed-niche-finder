"""Add source query traceability tables.

Revision ID: 0004_add_source_query_traceability
Revises: 0003_add_completed_no_evidence_status
Create Date: 2026-04-08 19:40:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0004_add_source_query_traceability"
down_revision = "0003_add_completed_no_evidence_status"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "source_queries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("provider_name", sa.String(length=100), nullable=False),
        sa.Column("query_text", sa.String(length=255), nullable=False),
        sa.Column("query_kind", sa.String(length=50), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("tags_json", sa.JSON(), nullable=False),
        sa.Column("item_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["research_runs.id"], name=op.f("fk_source_queries_run_id_research_runs"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_source_queries")),
        sa.UniqueConstraint("run_id", "provider_name", "query_text", "query_kind", name=op.f("uq_source_queries_run_provider_text_kind")),
    )
    op.create_index(op.f("ix_source_queries_created_at"), "source_queries", ["created_at"], unique=False)
    op.create_index(op.f("ix_source_queries_provider_name"), "source_queries", ["provider_name"], unique=False)
    op.create_index(op.f("ix_source_queries_run_id"), "source_queries", ["run_id"], unique=False)
    op.create_index("ix_source_queries_run_id_created_at", "source_queries", ["run_id", "created_at"], unique=False)
    op.create_index("ix_source_queries_run_id_provider_name", "source_queries", ["run_id", "provider_name"], unique=False)
    op.create_index("ix_source_queries_run_id_query_kind", "source_queries", ["run_id", "query_kind"], unique=False)

    op.create_table(
        "source_item_query_links",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_query_id", sa.Uuid(), nullable=False),
        sa.Column("source_item_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["source_item_id"], ["source_items.id"], name=op.f("fk_source_item_query_links_source_item_id_source_items"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_query_id"], ["source_queries.id"], name=op.f("fk_source_item_query_links_source_query_id_source_queries"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_source_item_query_links")),
        sa.UniqueConstraint("source_query_id", "source_item_id", name=op.f("uq_source_item_query_links_query_item")),
    )
    op.create_index(op.f("ix_source_item_query_links_created_at"), "source_item_query_links", ["created_at"], unique=False)
    op.create_index(op.f("ix_source_item_query_links_source_item_id"), "source_item_query_links", ["source_item_id"], unique=False)
    op.create_index("ix_source_item_query_links_source_item_id_created_at", "source_item_query_links", ["source_item_id", "created_at"], unique=False)
    op.create_index(op.f("ix_source_item_query_links_source_query_id"), "source_item_query_links", ["source_query_id"], unique=False)
    op.create_index("ix_source_item_query_links_source_query_id_created_at", "source_item_query_links", ["source_query_id", "created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_source_item_query_links_source_query_id_created_at", table_name="source_item_query_links")
    op.drop_index(op.f("ix_source_item_query_links_source_query_id"), table_name="source_item_query_links")
    op.drop_index("ix_source_item_query_links_source_item_id_created_at", table_name="source_item_query_links")
    op.drop_index(op.f("ix_source_item_query_links_source_item_id"), table_name="source_item_query_links")
    op.drop_index(op.f("ix_source_item_query_links_created_at"), table_name="source_item_query_links")
    op.drop_table("source_item_query_links")

    op.drop_index("ix_source_queries_run_id_query_kind", table_name="source_queries")
    op.drop_index("ix_source_queries_run_id_provider_name", table_name="source_queries")
    op.drop_index("ix_source_queries_run_id_created_at", table_name="source_queries")
    op.drop_index(op.f("ix_source_queries_run_id"), table_name="source_queries")
    op.drop_index(op.f("ix_source_queries_provider_name"), table_name="source_queries")
    op.drop_index(op.f("ix_source_queries_created_at"), table_name="source_queries")
    op.drop_table("source_queries")
