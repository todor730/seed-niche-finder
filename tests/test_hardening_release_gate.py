from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

from sqlalchemy import func, select

from app.db.models import (
    ProviderFailureRecord,
    ResearchRun,
    ResearchRunStatus,
    SourceItem,
    SourceItemQueryLink,
    SourceQuery,
)
from app.schemas.export import CreateExportRequest
from app.schemas.research import CreateResearchRunRequest
from app.services.export_service import ExportService
from app.services.research_service import ResearchService
from tests.test_research_service_evidence import (
    FakeProviderRegistry,
    make_batch,
    make_empty_batch,
    make_multi_query_traceability_batch,
)


def _create_service(session_factory, workspace: Path, *, batch) -> ResearchService:
    return ResearchService(
        session_factory,
        export_storage_path=str(workspace / "exports"),
        provider_registry=FakeProviderRegistry(batch),
    )


def test_release_gate_zero_evidence_runs_remain_honest_and_persist_failures(
    session_factory,
    workspace: Path,
    current_user,
) -> None:
    research_service = _create_service(
        session_factory,
        workspace,
        batch=make_empty_batch(include_failure=True),
    )
    export_service = ExportService(session_factory, export_storage_path=str(workspace / "exports"))

    created_run = research_service.create_run(
        current_user=current_user,
        payload=CreateResearchRunRequest(seed_niche="romance", config={"max_candidates": 20, "top_k": 5}),
    )
    run_id = UUID(str(created_run.id))

    with session_factory() as session:
        run = session.get(ResearchRun, run_id)
        source_item_count = session.scalar(select(func.count()).select_from(SourceItem).where(SourceItem.run_id == run_id))
        failure_count = session.scalar(
            select(func.count()).select_from(ProviderFailureRecord).where(ProviderFailureRecord.run_id == run_id)
        )

    assert run is not None
    assert run.status == ResearchRunStatus.COMPLETED_NO_EVIDENCE
    assert run.error_message == "No persisted source evidence was collected from the configured providers."
    assert (source_item_count or 0) == 0
    assert (failure_count or 0) == 1

    export_resource = export_service.create_export(
        current_user=current_user,
        run_id=run_id,
        payload=CreateExportRequest(format="json", scope="full_run"),
    )
    exported_data = json.loads(Path(export_resource.storage_uri or "").read_text(encoding="utf-8"))

    assert exported_data[0]["status"] == ResearchRunStatus.COMPLETED_NO_EVIDENCE.value
    assert exported_data[0]["insufficient_evidence"] is True
    assert exported_data[0]["niche_summaries"] == []
    assert exported_data[0]["keywords"] == []
    assert exported_data[0]["opportunities"] == []


def test_release_gate_traceability_and_immutable_exports_hold_for_evidence_runs(
    session_factory,
    workspace: Path,
    current_user,
) -> None:
    research_service = _create_service(
        session_factory,
        workspace,
        batch=make_multi_query_traceability_batch(),
    )
    export_service = ExportService(session_factory, export_storage_path=str(workspace / "exports"))

    created_run = research_service.create_run(
        current_user=current_user,
        payload=CreateResearchRunRequest(seed_niche="romance", config={"max_candidates": 20, "top_k": 5}),
    )
    run_id = UUID(str(created_run.id))

    with session_factory() as session:
        source_items = list(session.scalars(select(SourceItem).where(SourceItem.run_id == run_id)))
        source_queries = list(session.scalars(select(SourceQuery).where(SourceQuery.run_id == run_id)))
        source_item_query_links = list(
            session.scalars(select(SourceItemQueryLink).where(SourceItemQueryLink.source_item_id.in_([item.id for item in source_items])))
        )

    assert len(source_items) == 2
    assert len(source_queries) == 2
    assert len(source_item_query_links) == 3

    first_export = export_service.create_export(
        current_user=current_user,
        run_id=run_id,
        payload=CreateExportRequest(format="json", scope="full_run"),
    )
    second_export = export_service.create_export(
        current_user=current_user,
        run_id=run_id,
        payload=CreateExportRequest(format="json", scope="full_run"),
    )

    first_path = Path(first_export.storage_uri or "")
    second_path = Path(second_export.storage_uri or "")

    assert first_export.id != second_export.id
    assert first_path != second_path
    assert first_path.exists()
    assert second_path.exists()


def test_release_gate_ranked_run_still_materializes_real_outputs(
    session_factory,
    workspace: Path,
    current_user,
) -> None:
    research_service = _create_service(session_factory, workspace, batch=make_batch())

    created_run = research_service.create_run(
        current_user=current_user,
        payload=CreateResearchRunRequest(seed_niche="romance", config={"max_candidates": 20, "top_k": 5}),
    )
    run_id = UUID(str(created_run.id))

    with session_factory() as session:
        run = session.get(ResearchRun, run_id)

    assert run is not None
    assert run.status == ResearchRunStatus.COMPLETED
