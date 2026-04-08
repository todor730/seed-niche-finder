from __future__ import annotations

import importlib.util
from pathlib import Path

from sqlalchemy import inspect
from sqlalchemy.orm import configure_mappers

import app.db.models  # noqa: F401
from app.db.base import Base
from app.db.models import ExtractedSignal, NicheHypothesis, NicheScore, ResearchRun, SignalCluster, SourceItem


def test_evidence_tables_are_registered_in_metadata(engine) -> None:
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())

    assert {"source_items", "extracted_signals", "signal_clusters", "niche_hypotheses", "niche_scores"}.issubset(table_names)


def test_evidence_relationships_configure_cleanly() -> None:
    configure_mappers()

    assert ResearchRun.source_items.property.mapper.class_ is SourceItem
    assert ResearchRun.extracted_signals.property.mapper.class_ is ExtractedSignal
    assert ResearchRun.signal_clusters.property.mapper.class_ is SignalCluster
    assert ResearchRun.niche_hypotheses.property.mapper.class_ is NicheHypothesis
    assert ResearchRun.niche_scores.property.mapper.class_ is NicheScore
    assert SourceItem.extracted_signals.property.mapper.class_ is ExtractedSignal
    assert SignalCluster.niche_hypotheses.property.mapper.class_ is NicheHypothesis
    assert NicheHypothesis.niche_scores.property.mapper.class_ is NicheScore


def test_evidence_tables_have_expected_foreign_keys(engine) -> None:
    inspector = inspect(engine)

    source_item_fks = inspector.get_foreign_keys("source_items")
    extracted_signal_fks = inspector.get_foreign_keys("extracted_signals")
    niche_score_fks = inspector.get_foreign_keys("niche_scores")

    assert any(fk["referred_table"] == "research_runs" for fk in source_item_fks)
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


def test_evidence_tables_exist_in_base_metadata() -> None:
    assert {"source_items", "extracted_signals", "signal_clusters", "niche_hypotheses", "niche_scores"}.issubset(
        set(Base.metadata.tables.keys())
    )
