from __future__ import annotations

import importlib.util
from pathlib import Path

from sqlalchemy import inspect
from sqlalchemy.orm import configure_mappers

import app.db.models  # noqa: F401
from app.db.base import Base
from app.db.models import ExtractedSignal, NicheHypothesis, NicheScore, ProviderFailureRecord, ResearchRun, SignalCluster, SourceItem, SourceItemQueryLink, SourceQuery


def test_evidence_tables_are_registered_in_metadata(engine) -> None:
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())

    assert {
        "source_items",
        "source_queries",
        "source_item_query_links",
        "provider_failures",
        "extracted_signals",
        "signal_clusters",
        "niche_hypotheses",
        "niche_scores",
    }.issubset(table_names)


def test_evidence_relationships_configure_cleanly() -> None:
    configure_mappers()

    assert ResearchRun.source_items.property.mapper.class_ is SourceItem
    assert ResearchRun.source_queries.property.mapper.class_ is SourceQuery
    assert ResearchRun.provider_failures.property.mapper.class_ is ProviderFailureRecord
    assert ResearchRun.extracted_signals.property.mapper.class_ is ExtractedSignal
    assert ResearchRun.signal_clusters.property.mapper.class_ is SignalCluster
    assert ResearchRun.niche_hypotheses.property.mapper.class_ is NicheHypothesis
    assert ResearchRun.niche_scores.property.mapper.class_ is NicheScore
    assert SourceQuery.source_item_links.property.mapper.class_ is SourceItemQueryLink
    assert SourceItem.source_query_links.property.mapper.class_ is SourceItemQueryLink
    assert SourceItem.extracted_signals.property.mapper.class_ is ExtractedSignal
    assert SignalCluster.niche_hypotheses.property.mapper.class_ is NicheHypothesis
    assert NicheHypothesis.niche_scores.property.mapper.class_ is NicheScore


def test_evidence_tables_have_expected_foreign_keys(engine) -> None:
    inspector = inspect(engine)

    source_item_fks = inspector.get_foreign_keys("source_items")
    source_query_fks = inspector.get_foreign_keys("source_queries")
    source_item_query_link_fks = inspector.get_foreign_keys("source_item_query_links")
    provider_failure_fks = inspector.get_foreign_keys("provider_failures")
    extracted_signal_fks = inspector.get_foreign_keys("extracted_signals")
    niche_score_fks = inspector.get_foreign_keys("niche_scores")

    assert any(fk["referred_table"] == "research_runs" for fk in source_item_fks)
    assert any(fk["referred_table"] == "research_runs" for fk in source_query_fks)
    assert any(fk["referred_table"] == "source_queries" for fk in source_item_query_link_fks)
    assert any(fk["referred_table"] == "source_items" for fk in source_item_query_link_fks)
    assert any(fk["referred_table"] == "research_runs" for fk in provider_failure_fks)
    assert any(fk["referred_table"] == "source_items" for fk in extracted_signal_fks)
    assert any(fk["referred_table"] == "research_runs" for fk in extracted_signal_fks)
    assert any(fk["referred_table"] == "niche_hypotheses" for fk in niche_score_fks)


def test_evidence_migration_module_is_present() -> None:
    migration_path = Path.cwd() / "alembic" / "versions" / "0002_add_evidence_layer.py"
    spec = importlib.util.spec_from_file_location("migration_0002_add_evidence_layer", migration_path)
    assert spec is not None
    assert spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    assert migration.revision == "0002_add_evidence_layer"
    assert migration.down_revision == "0001_initial_schema"
    assert callable(migration.upgrade)
    assert callable(migration.downgrade)


def test_research_run_status_hardening_migration_is_present() -> None:
    migration_path = Path.cwd() / "alembic" / "versions" / "0003_add_completed_no_evidence_status.py"
    spec = importlib.util.spec_from_file_location("migration_0003_add_completed_no_evidence_status", migration_path)
    assert spec is not None
    assert spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    assert migration.revision == "0003_add_completed_no_evidence_status"
    assert migration.down_revision == "0002_add_evidence_layer"
    assert callable(migration.upgrade)
    assert callable(migration.downgrade)


def test_source_query_traceability_migration_is_present() -> None:
    migration_path = Path.cwd() / "alembic" / "versions" / "0004_add_source_query_traceability.py"
    spec = importlib.util.spec_from_file_location("migration_0004_add_source_query_traceability", migration_path)
    assert spec is not None
    assert spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    assert migration.revision == "0004_add_source_query_traceability"
    assert migration.down_revision == "0003_add_completed_no_evidence_status"
    assert callable(migration.upgrade)
    assert callable(migration.downgrade)


def test_provider_failures_migration_is_present() -> None:
    migration_path = Path.cwd() / "alembic" / "versions" / "0005_add_provider_failures_table.py"
    spec = importlib.util.spec_from_file_location("migration_0005_add_provider_failures_table", migration_path)
    assert spec is not None
    assert spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    assert migration.revision == "0005_add_provider_failures_table"
    assert migration.down_revision == "0004_add_source_query_traceability"
    assert callable(migration.upgrade)
    assert callable(migration.downgrade)


def test_evidence_tables_exist_in_base_metadata() -> None:
    assert {"source_items", "source_queries", "source_item_query_links", "provider_failures", "extracted_signals", "signal_clusters", "niche_hypotheses", "niche_scores"}.issubset(
        set(Base.metadata.tables.keys())
    )
