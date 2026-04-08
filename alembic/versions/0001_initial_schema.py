"""Initial schema.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-04-08 12:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


user_status_enum = postgresql.ENUM(
    "active",
    "inactive",
    name="user_status",
    create_type=False,
)
research_run_status_enum = postgresql.ENUM(
    "pending",
    "running",
    "completed",
    "failed",
    "cancelled",
    name="research_run_status",
    create_type=False,
)
keyword_candidate_status_enum = postgresql.ENUM(
    "discovered",
    "reviewed",
    "accepted",
    "rejected",
    name="keyword_candidate_status",
    create_type=False,
)
export_status_enum = postgresql.ENUM(
    "pending",
    "processing",
    "completed",
    "failed",
    name="export_status",
    create_type=False,
)
keyword_metrics_status_enum = postgresql.ENUM(
    "pending",
    "collected",
    "failed",
    name="keyword_metrics_status",
    create_type=False,
)
trend_metrics_status_enum = postgresql.ENUM(
    "pending",
    "collected",
    "failed",
    name="trend_metrics_status",
    create_type=False,
)
competitor_status_enum = postgresql.ENUM(
    "discovered",
    "analyzed",
    "excluded",
    name="competitor_status",
    create_type=False,
)
opportunity_status_enum = postgresql.ENUM(
    "identified",
    "ranked",
    "shortlisted",
    "rejected",
    name="opportunity_status",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()

    user_status_enum.create(bind, checkfirst=True)
    research_run_status_enum.create(bind, checkfirst=True)
    keyword_candidate_status_enum.create(bind, checkfirst=True)
    export_status_enum.create(bind, checkfirst=True)
    keyword_metrics_status_enum.create(bind, checkfirst=True)
    trend_metrics_status_enum.create(bind, checkfirst=True)
    competitor_status_enum.create(bind, checkfirst=True)
    opportunity_status_enum.create(bind, checkfirst=True)

    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=True),
        sa.Column("status", user_status_enum, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
    )
    op.create_index(op.f("ix_users_created_at"), "users", ["created_at"], unique=False)
    op.create_index(op.f("ix_users_status"), "users", ["status"], unique=False)

    op.create_table(
        "research_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("status", research_run_status_enum, nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_research_runs_user_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_research_runs")),
    )
    op.create_index(op.f("ix_research_runs_created_at"), "research_runs", ["created_at"], unique=False)
    op.create_index(op.f("ix_research_runs_status"), "research_runs", ["status"], unique=False)
    op.create_index(op.f("ix_research_runs_user_id"), "research_runs", ["user_id"], unique=False)
    op.create_index("ix_research_runs_user_id_created_at", "research_runs", ["user_id", "created_at"], unique=False)
    op.create_index("ix_research_runs_user_id_status", "research_runs", ["user_id", "status"], unique=False)

    op.create_table(
        "keyword_candidates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("keyword_text", sa.String(length=255), nullable=False),
        sa.Column("status", keyword_candidate_status_enum, nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["research_runs.id"],
            name=op.f("fk_keyword_candidates_run_id_research_runs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_keyword_candidates")),
    )
    op.create_index(op.f("ix_keyword_candidates_created_at"), "keyword_candidates", ["created_at"], unique=False)
    op.create_index(op.f("ix_keyword_candidates_run_id"), "keyword_candidates", ["run_id"], unique=False)
    op.create_index("ix_keyword_candidates_run_id_created_at", "keyword_candidates", ["run_id", "created_at"], unique=False)
    op.create_index("ix_keyword_candidates_run_id_status", "keyword_candidates", ["run_id", "status"], unique=False)
    op.create_index(op.f("ix_keyword_candidates_status"), "keyword_candidates", ["status"], unique=False)

    op.create_table(
        "keyword_metrics",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("keyword_candidate_id", sa.Uuid(), nullable=False),
        sa.Column("provider_name", sa.String(length=100), nullable=True),
        sa.Column("status", keyword_metrics_status_enum, nullable=False),
        sa.Column("search_volume", sa.Integer(), nullable=True),
        sa.Column("competition_score", sa.Float(), nullable=True),
        sa.Column("cpc_usd", sa.Float(), nullable=True),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["keyword_candidate_id"],
            ["keyword_candidates.id"],
            name=op.f("fk_keyword_metrics_keyword_candidate_id_keyword_candidates"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["research_runs.id"],
            name=op.f("fk_keyword_metrics_run_id_research_runs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_keyword_metrics")),
    )
    op.create_index(op.f("ix_keyword_metrics_created_at"), "keyword_metrics", ["created_at"], unique=False)
    op.create_index(op.f("ix_keyword_metrics_keyword_candidate_id"), "keyword_metrics", ["keyword_candidate_id"], unique=False)
    op.create_index(
        "ix_keyword_metrics_keyword_candidate_id_created_at",
        "keyword_metrics",
        ["keyword_candidate_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_keyword_metrics_keyword_candidate_id_status",
        "keyword_metrics",
        ["keyword_candidate_id", "status"],
        unique=False,
    )
    op.create_index(op.f("ix_keyword_metrics_run_id"), "keyword_metrics", ["run_id"], unique=False)
    op.create_index("ix_keyword_metrics_run_id_created_at", "keyword_metrics", ["run_id", "created_at"], unique=False)
    op.create_index("ix_keyword_metrics_run_id_status", "keyword_metrics", ["run_id", "status"], unique=False)
    op.create_index(op.f("ix_keyword_metrics_status"), "keyword_metrics", ["status"], unique=False)

    op.create_table(
        "trend_metrics",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("keyword_candidate_id", sa.Uuid(), nullable=False),
        sa.Column("provider_name", sa.String(length=100), nullable=True),
        sa.Column("status", trend_metrics_status_enum, nullable=False),
        sa.Column("trend_score", sa.Float(), nullable=True),
        sa.Column("trend_change_30d", sa.Float(), nullable=True),
        sa.Column("trend_change_90d", sa.Float(), nullable=True),
        sa.Column("seasonality_score", sa.Float(), nullable=True),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["keyword_candidate_id"],
            ["keyword_candidates.id"],
            name=op.f("fk_trend_metrics_keyword_candidate_id_keyword_candidates"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["research_runs.id"],
            name=op.f("fk_trend_metrics_run_id_research_runs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_trend_metrics")),
    )
    op.create_index(op.f("ix_trend_metrics_created_at"), "trend_metrics", ["created_at"], unique=False)
    op.create_index(op.f("ix_trend_metrics_keyword_candidate_id"), "trend_metrics", ["keyword_candidate_id"], unique=False)
    op.create_index(
        "ix_trend_metrics_keyword_candidate_id_created_at",
        "trend_metrics",
        ["keyword_candidate_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_trend_metrics_keyword_candidate_id_status",
        "trend_metrics",
        ["keyword_candidate_id", "status"],
        unique=False,
    )
    op.create_index(op.f("ix_trend_metrics_run_id"), "trend_metrics", ["run_id"], unique=False)
    op.create_index("ix_trend_metrics_run_id_created_at", "trend_metrics", ["run_id", "created_at"], unique=False)
    op.create_index("ix_trend_metrics_run_id_status", "trend_metrics", ["run_id", "status"], unique=False)
    op.create_index(op.f("ix_trend_metrics_status"), "trend_metrics", ["status"], unique=False)

    op.create_table(
        "competitors",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("keyword_candidate_id", sa.Uuid(), nullable=False),
        sa.Column("competitor_name", sa.String(length=255), nullable=False),
        sa.Column("marketplace", sa.String(length=100), nullable=True),
        sa.Column("source_url", sa.String(length=1024), nullable=True),
        sa.Column("status", competitor_status_enum, nullable=False),
        sa.Column("average_rating", sa.Float(), nullable=True),
        sa.Column("review_count", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["keyword_candidate_id"],
            ["keyword_candidates.id"],
            name=op.f("fk_competitors_keyword_candidate_id_keyword_candidates"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["research_runs.id"],
            name=op.f("fk_competitors_run_id_research_runs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_competitors")),
    )
    op.create_index(op.f("ix_competitors_created_at"), "competitors", ["created_at"], unique=False)
    op.create_index(op.f("ix_competitors_keyword_candidate_id"), "competitors", ["keyword_candidate_id"], unique=False)
    op.create_index(
        "ix_competitors_keyword_candidate_id_created_at",
        "competitors",
        ["keyword_candidate_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_competitors_keyword_candidate_id_status",
        "competitors",
        ["keyword_candidate_id", "status"],
        unique=False,
    )
    op.create_index(op.f("ix_competitors_run_id"), "competitors", ["run_id"], unique=False)
    op.create_index("ix_competitors_run_id_created_at", "competitors", ["run_id", "created_at"], unique=False)
    op.create_index("ix_competitors_run_id_status", "competitors", ["run_id", "status"], unique=False)
    op.create_index(op.f("ix_competitors_status"), "competitors", ["status"], unique=False)

    op.create_table(
        "opportunities",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("keyword_candidate_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("status", opportunity_status_enum, nullable=False),
        sa.Column("demand_score", sa.Float(), nullable=True),
        sa.Column("trend_score", sa.Float(), nullable=True),
        sa.Column("intent_score", sa.Float(), nullable=True),
        sa.Column("hook_score", sa.Float(), nullable=True),
        sa.Column("monetization_score", sa.Float(), nullable=True),
        sa.Column("competition_score", sa.Float(), nullable=True),
        sa.Column("opportunity_score", sa.Float(), nullable=True),
        sa.Column("rationale_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["keyword_candidate_id"],
            ["keyword_candidates.id"],
            name=op.f("fk_opportunities_keyword_candidate_id_keyword_candidates"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["research_runs.id"],
            name=op.f("fk_opportunities_run_id_research_runs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_opportunities")),
    )
    op.create_index(op.f("ix_opportunities_created_at"), "opportunities", ["created_at"], unique=False)
    op.create_index(op.f("ix_opportunities_keyword_candidate_id"), "opportunities", ["keyword_candidate_id"], unique=False)
    op.create_index(
        "ix_opportunities_keyword_candidate_id_created_at",
        "opportunities",
        ["keyword_candidate_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_opportunities_keyword_candidate_id_opportunity_score",
        "opportunities",
        ["keyword_candidate_id", "opportunity_score"],
        unique=False,
    )
    op.create_index(
        "ix_opportunities_keyword_candidate_id_status",
        "opportunities",
        ["keyword_candidate_id", "status"],
        unique=False,
    )
    op.create_index(op.f("ix_opportunities_opportunity_score"), "opportunities", ["opportunity_score"], unique=False)
    op.create_index(op.f("ix_opportunities_run_id"), "opportunities", ["run_id"], unique=False)
    op.create_index("ix_opportunities_run_id_created_at", "opportunities", ["run_id", "created_at"], unique=False)
    op.create_index(
        "ix_opportunities_run_id_opportunity_score",
        "opportunities",
        ["run_id", "opportunity_score"],
        unique=False,
    )
    op.create_index("ix_opportunities_run_id_status", "opportunities", ["run_id", "status"], unique=False)
    op.create_index(op.f("ix_opportunities_status"), "opportunities", ["status"], unique=False)
    op.create_index(
        "ix_opportunities_status_opportunity_score",
        "opportunities",
        ["status", "opportunity_score"],
        unique=False,
    )

    op.create_table(
        "exports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("export_format", sa.String(length=50), nullable=False),
        sa.Column("storage_uri", sa.String(length=1024), nullable=True),
        sa.Column("status", export_status_enum, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["research_runs.id"], name=op.f("fk_exports_run_id_research_runs"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_exports")),
    )
    op.create_index(op.f("ix_exports_created_at"), "exports", ["created_at"], unique=False)
    op.create_index(op.f("ix_exports_run_id"), "exports", ["run_id"], unique=False)
    op.create_index("ix_exports_run_id_created_at", "exports", ["run_id", "created_at"], unique=False)
    op.create_index("ix_exports_run_id_status", "exports", ["run_id", "status"], unique=False)
    op.create_index(op.f("ix_exports_status"), "exports", ["status"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()

    op.drop_index(op.f("ix_exports_status"), table_name="exports")
    op.drop_index("ix_exports_run_id_status", table_name="exports")
    op.drop_index("ix_exports_run_id_created_at", table_name="exports")
    op.drop_index(op.f("ix_exports_run_id"), table_name="exports")
    op.drop_index(op.f("ix_exports_created_at"), table_name="exports")
    op.drop_table("exports")

    op.drop_index("ix_opportunities_status_opportunity_score", table_name="opportunities")
    op.drop_index(op.f("ix_opportunities_status"), table_name="opportunities")
    op.drop_index("ix_opportunities_run_id_status", table_name="opportunities")
    op.drop_index("ix_opportunities_run_id_opportunity_score", table_name="opportunities")
    op.drop_index("ix_opportunities_run_id_created_at", table_name="opportunities")
    op.drop_index(op.f("ix_opportunities_run_id"), table_name="opportunities")
    op.drop_index(op.f("ix_opportunities_opportunity_score"), table_name="opportunities")
    op.drop_index("ix_opportunities_keyword_candidate_id_status", table_name="opportunities")
    op.drop_index("ix_opportunities_keyword_candidate_id_opportunity_score", table_name="opportunities")
    op.drop_index("ix_opportunities_keyword_candidate_id_created_at", table_name="opportunities")
    op.drop_index(op.f("ix_opportunities_keyword_candidate_id"), table_name="opportunities")
    op.drop_index(op.f("ix_opportunities_created_at"), table_name="opportunities")
    op.drop_table("opportunities")

    op.drop_index(op.f("ix_competitors_status"), table_name="competitors")
    op.drop_index("ix_competitors_run_id_status", table_name="competitors")
    op.drop_index("ix_competitors_run_id_created_at", table_name="competitors")
    op.drop_index(op.f("ix_competitors_run_id"), table_name="competitors")
    op.drop_index("ix_competitors_keyword_candidate_id_status", table_name="competitors")
    op.drop_index("ix_competitors_keyword_candidate_id_created_at", table_name="competitors")
    op.drop_index(op.f("ix_competitors_keyword_candidate_id"), table_name="competitors")
    op.drop_index(op.f("ix_competitors_created_at"), table_name="competitors")
    op.drop_table("competitors")

    op.drop_index(op.f("ix_trend_metrics_status"), table_name="trend_metrics")
    op.drop_index("ix_trend_metrics_run_id_status", table_name="trend_metrics")
    op.drop_index("ix_trend_metrics_run_id_created_at", table_name="trend_metrics")
    op.drop_index(op.f("ix_trend_metrics_run_id"), table_name="trend_metrics")
    op.drop_index("ix_trend_metrics_keyword_candidate_id_status", table_name="trend_metrics")
    op.drop_index("ix_trend_metrics_keyword_candidate_id_created_at", table_name="trend_metrics")
    op.drop_index(op.f("ix_trend_metrics_keyword_candidate_id"), table_name="trend_metrics")
    op.drop_index(op.f("ix_trend_metrics_created_at"), table_name="trend_metrics")
    op.drop_table("trend_metrics")

    op.drop_index(op.f("ix_keyword_metrics_status"), table_name="keyword_metrics")
    op.drop_index("ix_keyword_metrics_run_id_status", table_name="keyword_metrics")
    op.drop_index("ix_keyword_metrics_run_id_created_at", table_name="keyword_metrics")
    op.drop_index(op.f("ix_keyword_metrics_run_id"), table_name="keyword_metrics")
    op.drop_index("ix_keyword_metrics_keyword_candidate_id_status", table_name="keyword_metrics")
    op.drop_index("ix_keyword_metrics_keyword_candidate_id_created_at", table_name="keyword_metrics")
    op.drop_index(op.f("ix_keyword_metrics_keyword_candidate_id"), table_name="keyword_metrics")
    op.drop_index(op.f("ix_keyword_metrics_created_at"), table_name="keyword_metrics")
    op.drop_table("keyword_metrics")

    op.drop_index(op.f("ix_keyword_candidates_status"), table_name="keyword_candidates")
    op.drop_index("ix_keyword_candidates_run_id_status", table_name="keyword_candidates")
    op.drop_index("ix_keyword_candidates_run_id_created_at", table_name="keyword_candidates")
    op.drop_index(op.f("ix_keyword_candidates_run_id"), table_name="keyword_candidates")
    op.drop_index(op.f("ix_keyword_candidates_created_at"), table_name="keyword_candidates")
    op.drop_table("keyword_candidates")

    op.drop_index("ix_research_runs_user_id_status", table_name="research_runs")
    op.drop_index("ix_research_runs_user_id_created_at", table_name="research_runs")
    op.drop_index(op.f("ix_research_runs_user_id"), table_name="research_runs")
    op.drop_index(op.f("ix_research_runs_status"), table_name="research_runs")
    op.drop_index(op.f("ix_research_runs_created_at"), table_name="research_runs")
    op.drop_table("research_runs")

    op.drop_index(op.f("ix_users_status"), table_name="users")
    op.drop_index(op.f("ix_users_created_at"), table_name="users")
    op.drop_table("users")

    opportunity_status_enum.drop(bind, checkfirst=True)
    competitor_status_enum.drop(bind, checkfirst=True)
    trend_metrics_status_enum.drop(bind, checkfirst=True)
    keyword_metrics_status_enum.drop(bind, checkfirst=True)
    export_status_enum.drop(bind, checkfirst=True)
    keyword_candidate_status_enum.drop(bind, checkfirst=True)
    research_run_status_enum.drop(bind, checkfirst=True)
    user_status_enum.drop(bind, checkfirst=True)
