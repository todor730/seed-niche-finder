"""Add evidence layer tables.

Revision ID: 0002_add_evidence_layer
Revises: 0001_initial_schema
Create Date: 2026-04-08 16:10:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0002_add_evidence_layer"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


source_item_status_enum = sa.Enum(
    "fetched",
    "extracted",
    "clustered",
    "discarded",
    name="source_item_status",
    native_enum=False,
)
niche_hypothesis_status_enum = sa.Enum(
    "identified",
    "scored",
    "shortlisted",
    "rejected",
    name="niche_hypothesis_status",
    native_enum=False,
)


def upgrade() -> None:
    op.create_table(
        "source_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("provider_name", sa.String(length=100), nullable=False),
        sa.Column("query_text", sa.String(length=255), nullable=False),
        sa.Column("query_kind", sa.String(length=50), nullable=True),
        sa.Column("provider_item_id", sa.String(length=255), nullable=True),
        sa.Column("dedupe_key", sa.String(length=255), nullable=False),
        sa.Column("source_url", sa.String(length=1024), nullable=True),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("subtitle", sa.String(length=512), nullable=True),
        sa.Column("authors_json", sa.JSON(), nullable=False),
        sa.Column("categories_json", sa.JSON(), nullable=False),
        sa.Column("description_text", sa.Text(), nullable=True),
        sa.Column("content_text", sa.Text(), nullable=False),
        sa.Column("published_date_raw", sa.String(length=50), nullable=True),
        sa.Column("average_rating", sa.Float(), nullable=True),
        sa.Column("rating_count", sa.Integer(), nullable=True),
        sa.Column("review_count", sa.Integer(), nullable=True),
        sa.Column("raw_payload_json", sa.JSON(), nullable=False),
        sa.Column("status", source_item_status_enum, nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "average_rating IS NULL OR (average_rating >= 0 AND average_rating <= 5)",
            name=op.f("ck_source_items_average_rating_range"),
        ),
        sa.CheckConstraint("rating_count IS NULL OR rating_count >= 0", name=op.f("ck_source_items_rating_count_non_negative")),
        sa.CheckConstraint("review_count IS NULL OR review_count >= 0", name=op.f("ck_source_items_review_count_non_negative")),
        sa.ForeignKeyConstraint(["run_id"], ["research_runs.id"], name=op.f("fk_source_items_run_id_research_runs"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_source_items")),
        sa.UniqueConstraint("run_id", "provider_name", "dedupe_key", name=op.f("uq_source_items_run_provider_dedupe_key")),
    )
    op.create_index(op.f("ix_source_items_created_at"), "source_items", ["created_at"], unique=False)
    op.create_index(op.f("ix_source_items_fetched_at"), "source_items", ["fetched_at"], unique=False)
    op.create_index(op.f("ix_source_items_provider_name"), "source_items", ["provider_name"], unique=False)
    op.create_index(op.f("ix_source_items_run_id"), "source_items", ["run_id"], unique=False)
    op.create_index("ix_source_items_run_id_fetched_at", "source_items", ["run_id", "fetched_at"], unique=False)
    op.create_index("ix_source_items_run_id_provider_name", "source_items", ["run_id", "provider_name"], unique=False)
    op.create_index("ix_source_items_run_id_query_text", "source_items", ["run_id", "query_text"], unique=False)
    op.create_index("ix_source_items_run_id_status", "source_items", ["run_id", "status"], unique=False)
    op.create_index(op.f("ix_source_items_status"), "source_items", ["status"], unique=False)

    op.create_table(
        "signal_clusters",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("signal_type", sa.String(length=100), nullable=False),
        sa.Column("canonical_label", sa.String(length=255), nullable=False),
        sa.Column("aliases_json", sa.JSON(), nullable=False),
        sa.Column("source_count", sa.Integer(), nullable=False),
        sa.Column("item_count", sa.Integer(), nullable=False),
        sa.Column("avg_confidence", sa.Float(), nullable=False),
        sa.Column("saturation_score", sa.Float(), nullable=False),
        sa.Column("novelty_score", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("source_count >= 0", name=op.f("ck_signal_clusters_source_count_non_negative")),
        sa.CheckConstraint("item_count >= 0", name=op.f("ck_signal_clusters_item_count_non_negative")),
        sa.CheckConstraint("avg_confidence >= 0 AND avg_confidence <= 1", name=op.f("ck_signal_clusters_avg_confidence_range")),
        sa.CheckConstraint("saturation_score >= 0 AND saturation_score <= 100", name=op.f("ck_signal_clusters_saturation_score_range")),
        sa.CheckConstraint("novelty_score >= 0 AND novelty_score <= 100", name=op.f("ck_signal_clusters_novelty_score_range")),
        sa.ForeignKeyConstraint(["run_id"], ["research_runs.id"], name=op.f("fk_signal_clusters_run_id_research_runs"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_signal_clusters")),
        sa.UniqueConstraint("run_id", "signal_type", "canonical_label", name=op.f("uq_signal_clusters_run_type_canonical_label")),
    )
    op.create_index(op.f("ix_signal_clusters_created_at"), "signal_clusters", ["created_at"], unique=False)
    op.create_index(op.f("ix_signal_clusters_run_id"), "signal_clusters", ["run_id"], unique=False)
    op.create_index("ix_signal_clusters_run_id_avg_confidence", "signal_clusters", ["run_id", "avg_confidence"], unique=False)
    op.create_index("ix_signal_clusters_run_id_created_at", "signal_clusters", ["run_id", "created_at"], unique=False)
    op.create_index("ix_signal_clusters_run_id_novelty_score", "signal_clusters", ["run_id", "novelty_score"], unique=False)
    op.create_index("ix_signal_clusters_run_id_signal_type", "signal_clusters", ["run_id", "signal_type"], unique=False)
    op.create_index("ix_signal_clusters_run_id_source_count", "signal_clusters", ["run_id", "source_count"], unique=False)
    op.create_index(op.f("ix_signal_clusters_signal_type"), "signal_clusters", ["signal_type"], unique=False)

    op.create_table(
        "extracted_signals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("source_item_id", sa.Uuid(), nullable=False),
        sa.Column("cluster_id", sa.Uuid(), nullable=True),
        sa.Column("signal_type", sa.String(length=100), nullable=False),
        sa.Column("signal_value", sa.String(length=512), nullable=False),
        sa.Column("normalized_value", sa.String(length=255), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("extraction_method", sa.String(length=100), nullable=False),
        sa.Column("evidence_span", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name=op.f("ck_extracted_signals_confidence_range")),
        sa.ForeignKeyConstraint(["cluster_id"], ["signal_clusters.id"], name=op.f("fk_extracted_signals_cluster_id_signal_clusters"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["run_id"], ["research_runs.id"], name=op.f("fk_extracted_signals_run_id_research_runs"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_item_id"], ["source_items.id"], name=op.f("fk_extracted_signals_source_item_id_source_items"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_extracted_signals")),
        sa.UniqueConstraint(
            "source_item_id",
            "signal_type",
            "normalized_value",
            "extraction_method",
            name=op.f("uq_extracted_signals_source_item_type_normalized_method"),
        ),
    )
    op.create_index(op.f("ix_extracted_signals_cluster_id"), "extracted_signals", ["cluster_id"], unique=False)
    op.create_index("ix_extracted_signals_cluster_id_confidence", "extracted_signals", ["cluster_id", "confidence"], unique=False)
    op.create_index(op.f("ix_extracted_signals_created_at"), "extracted_signals", ["created_at"], unique=False)
    op.create_index(op.f("ix_extracted_signals_run_id"), "extracted_signals", ["run_id"], unique=False)
    op.create_index("ix_extracted_signals_run_id_confidence", "extracted_signals", ["run_id", "confidence"], unique=False)
    op.create_index("ix_extracted_signals_run_id_created_at", "extracted_signals", ["run_id", "created_at"], unique=False)
    op.create_index("ix_extracted_signals_run_id_normalized_value", "extracted_signals", ["run_id", "normalized_value"], unique=False)
    op.create_index("ix_extracted_signals_run_id_signal_type", "extracted_signals", ["run_id", "signal_type"], unique=False)
    op.create_index(op.f("ix_extracted_signals_signal_type"), "extracted_signals", ["signal_type"], unique=False)
    op.create_index(op.f("ix_extracted_signals_source_item_id"), "extracted_signals", ["source_item_id"], unique=False)

    op.create_table(
        "niche_hypotheses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("primary_cluster_id", sa.Uuid(), nullable=False),
        sa.Column("hypothesis_label", sa.String(length=255), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("rationale_json", sa.JSON(), nullable=False),
        sa.Column("evidence_count", sa.Integer(), nullable=False),
        sa.Column("source_count", sa.Integer(), nullable=False),
        sa.Column("overall_score", sa.Float(), nullable=True),
        sa.Column("rank_position", sa.Integer(), nullable=True),
        sa.Column("status", niche_hypothesis_status_enum, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("evidence_count >= 0", name=op.f("ck_niche_hypotheses_evidence_count_non_negative")),
        sa.CheckConstraint("source_count >= 0", name=op.f("ck_niche_hypotheses_source_count_non_negative")),
        sa.CheckConstraint(
            "overall_score IS NULL OR (overall_score >= 0 AND overall_score <= 100)",
            name=op.f("ck_niche_hypotheses_overall_score_range"),
        ),
        sa.CheckConstraint("rank_position IS NULL OR rank_position >= 1", name=op.f("ck_niche_hypotheses_rank_position_positive")),
        sa.ForeignKeyConstraint(["primary_cluster_id"], ["signal_clusters.id"], name=op.f("fk_niche_hypotheses_primary_cluster_id_signal_clusters"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["research_runs.id"], name=op.f("fk_niche_hypotheses_run_id_research_runs"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_niche_hypotheses")),
        sa.UniqueConstraint("run_id", "hypothesis_label", name=op.f("uq_niche_hypotheses_run_hypothesis_label")),
    )
    op.create_index(op.f("ix_niche_hypotheses_created_at"), "niche_hypotheses", ["created_at"], unique=False)
    op.create_index(op.f("ix_niche_hypotheses_overall_score"), "niche_hypotheses", ["overall_score"], unique=False)
    op.create_index(op.f("ix_niche_hypotheses_primary_cluster_id"), "niche_hypotheses", ["primary_cluster_id"], unique=False)
    op.create_index("ix_niche_hypotheses_primary_cluster_id_status", "niche_hypotheses", ["primary_cluster_id", "status"], unique=False)
    op.create_index(op.f("ix_niche_hypotheses_rank_position"), "niche_hypotheses", ["rank_position"], unique=False)
    op.create_index(op.f("ix_niche_hypotheses_run_id"), "niche_hypotheses", ["run_id"], unique=False)
    op.create_index("ix_niche_hypotheses_run_id_created_at", "niche_hypotheses", ["run_id", "created_at"], unique=False)
    op.create_index("ix_niche_hypotheses_run_id_overall_score", "niche_hypotheses", ["run_id", "overall_score"], unique=False)
    op.create_index("ix_niche_hypotheses_run_id_rank_position", "niche_hypotheses", ["run_id", "rank_position"], unique=False)
    op.create_index("ix_niche_hypotheses_run_id_status", "niche_hypotheses", ["run_id", "status"], unique=False)
    op.create_index(op.f("ix_niche_hypotheses_status"), "niche_hypotheses", ["status"], unique=False)

    op.create_table(
        "niche_scores",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("niche_hypothesis_id", sa.Uuid(), nullable=False),
        sa.Column("score_type", sa.String(length=100), nullable=False),
        sa.Column("score_value", sa.Float(), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False),
        sa.Column("weighted_score", sa.Float(), nullable=True),
        sa.Column("evidence_count", sa.Integer(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("evidence_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("score_value >= 0 AND score_value <= 100", name=op.f("ck_niche_scores_score_value_range")),
        sa.CheckConstraint("weight >= 0 AND weight <= 1", name=op.f("ck_niche_scores_weight_range")),
        sa.CheckConstraint(
            "weighted_score IS NULL OR (weighted_score >= 0 AND weighted_score <= 100)",
            name=op.f("ck_niche_scores_weighted_score_range"),
        ),
        sa.CheckConstraint("evidence_count >= 0", name=op.f("ck_niche_scores_evidence_count_non_negative")),
        sa.ForeignKeyConstraint(["niche_hypothesis_id"], ["niche_hypotheses.id"], name=op.f("fk_niche_scores_niche_hypothesis_id_niche_hypotheses"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["research_runs.id"], name=op.f("fk_niche_scores_run_id_research_runs"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_niche_scores")),
        sa.UniqueConstraint("niche_hypothesis_id", "score_type", name=op.f("uq_niche_scores_hypothesis_id_score_type")),
    )
    op.create_index(op.f("ix_niche_scores_created_at"), "niche_scores", ["created_at"], unique=False)
    op.create_index(op.f("ix_niche_scores_niche_hypothesis_id"), "niche_scores", ["niche_hypothesis_id"], unique=False)
    op.create_index("ix_niche_scores_hypothesis_id_score_value", "niche_scores", ["niche_hypothesis_id", "score_value"], unique=False)
    op.create_index(op.f("ix_niche_scores_run_id"), "niche_scores", ["run_id"], unique=False)
    op.create_index("ix_niche_scores_run_id_created_at", "niche_scores", ["run_id", "created_at"], unique=False)
    op.create_index("ix_niche_scores_run_id_score_type", "niche_scores", ["run_id", "score_type"], unique=False)
    op.create_index("ix_niche_scores_run_id_score_value", "niche_scores", ["run_id", "score_value"], unique=False)
    op.create_index(op.f("ix_niche_scores_score_type"), "niche_scores", ["score_type"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_niche_scores_score_type"), table_name="niche_scores")
    op.drop_index("ix_niche_scores_run_id_score_value", table_name="niche_scores")
    op.drop_index("ix_niche_scores_run_id_score_type", table_name="niche_scores")
    op.drop_index("ix_niche_scores_run_id_created_at", table_name="niche_scores")
    op.drop_index(op.f("ix_niche_scores_run_id"), table_name="niche_scores")
    op.drop_index("ix_niche_scores_hypothesis_id_score_value", table_name="niche_scores")
    op.drop_index(op.f("ix_niche_scores_niche_hypothesis_id"), table_name="niche_scores")
    op.drop_index(op.f("ix_niche_scores_created_at"), table_name="niche_scores")
    op.drop_table("niche_scores")

    op.drop_index(op.f("ix_niche_hypotheses_status"), table_name="niche_hypotheses")
    op.drop_index("ix_niche_hypotheses_run_id_status", table_name="niche_hypotheses")
    op.drop_index("ix_niche_hypotheses_run_id_rank_position", table_name="niche_hypotheses")
    op.drop_index("ix_niche_hypotheses_run_id_overall_score", table_name="niche_hypotheses")
    op.drop_index("ix_niche_hypotheses_run_id_created_at", table_name="niche_hypotheses")
    op.drop_index(op.f("ix_niche_hypotheses_run_id"), table_name="niche_hypotheses")
    op.drop_index(op.f("ix_niche_hypotheses_rank_position"), table_name="niche_hypotheses")
    op.drop_index("ix_niche_hypotheses_primary_cluster_id_status", table_name="niche_hypotheses")
    op.drop_index(op.f("ix_niche_hypotheses_primary_cluster_id"), table_name="niche_hypotheses")
    op.drop_index(op.f("ix_niche_hypotheses_overall_score"), table_name="niche_hypotheses")
    op.drop_index(op.f("ix_niche_hypotheses_created_at"), table_name="niche_hypotheses")
    op.drop_table("niche_hypotheses")

    op.drop_index(op.f("ix_extracted_signals_source_item_id"), table_name="extracted_signals")
    op.drop_index(op.f("ix_extracted_signals_signal_type"), table_name="extracted_signals")
    op.drop_index("ix_extracted_signals_run_id_signal_type", table_name="extracted_signals")
    op.drop_index("ix_extracted_signals_run_id_normalized_value", table_name="extracted_signals")
    op.drop_index("ix_extracted_signals_run_id_created_at", table_name="extracted_signals")
    op.drop_index("ix_extracted_signals_run_id_confidence", table_name="extracted_signals")
    op.drop_index(op.f("ix_extracted_signals_run_id"), table_name="extracted_signals")
    op.drop_index(op.f("ix_extracted_signals_created_at"), table_name="extracted_signals")
    op.drop_index("ix_extracted_signals_cluster_id_confidence", table_name="extracted_signals")
    op.drop_index(op.f("ix_extracted_signals_cluster_id"), table_name="extracted_signals")
    op.drop_table("extracted_signals")

    op.drop_index(op.f("ix_signal_clusters_signal_type"), table_name="signal_clusters")
    op.drop_index("ix_signal_clusters_run_id_source_count", table_name="signal_clusters")
    op.drop_index("ix_signal_clusters_run_id_signal_type", table_name="signal_clusters")
    op.drop_index("ix_signal_clusters_run_id_novelty_score", table_name="signal_clusters")
    op.drop_index("ix_signal_clusters_run_id_created_at", table_name="signal_clusters")
    op.drop_index("ix_signal_clusters_run_id_avg_confidence", table_name="signal_clusters")
    op.drop_index(op.f("ix_signal_clusters_run_id"), table_name="signal_clusters")
    op.drop_index(op.f("ix_signal_clusters_created_at"), table_name="signal_clusters")
    op.drop_table("signal_clusters")

    op.drop_index(op.f("ix_source_items_status"), table_name="source_items")
    op.drop_index("ix_source_items_run_id_status", table_name="source_items")
    op.drop_index("ix_source_items_run_id_query_text", table_name="source_items")
    op.drop_index("ix_source_items_run_id_provider_name", table_name="source_items")
    op.drop_index("ix_source_items_run_id_fetched_at", table_name="source_items")
    op.drop_index(op.f("ix_source_items_run_id"), table_name="source_items")
    op.drop_index(op.f("ix_source_items_provider_name"), table_name="source_items")
    op.drop_index(op.f("ix_source_items_fetched_at"), table_name="source_items")
    op.drop_index(op.f("ix_source_items_created_at"), table_name="source_items")
    op.drop_table("source_items")
