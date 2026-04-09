from __future__ import annotations

from uuid import UUID

from app.api.dependencies import CurrentUser
from app.schemas.export import CreateExportRequest
from app.schemas.research import CreateResearchRunRequest
from app.services.export_service import ExportService
from app.services.research_service import ResearchService
from tests.test_research_service_evidence import FakeProviderRegistry, make_batch, make_empty_batch


def _create_run(
    *,
    session_factory,
    workspace,
    current_user: CurrentUser,
    batch,
    seed_niche: str,
):
    service = ResearchService(
        session_factory,
        export_storage_path=str(workspace / "exports"),
        provider_registry=FakeProviderRegistry(batch),
    )
    return service.create_run(
        current_user=current_user,
        payload=CreateResearchRunRequest(seed_niche=seed_niche, config={"max_candidates": 20, "top_k": 5}),
    )


def test_list_runs_returns_correct_totals_and_precomputed_summaries(
    session_factory,
    workspace,
    current_user: CurrentUser,
) -> None:
    service = ResearchService(
        session_factory,
        export_storage_path=str(workspace / "exports"),
        provider_registry=FakeProviderRegistry(make_batch()),
    )
    first_run = service.create_run(
        current_user=current_user,
        payload=CreateResearchRunRequest(seed_niche="romance", config={"max_candidates": 20, "top_k": 5}),
    )
    _create_run(
        session_factory=session_factory,
        workspace=workspace,
        current_user=current_user,
        batch=make_empty_batch(include_failure=True),
        seed_niche="sleep",
    )

    listed = service.list_runs(current_user=current_user, status=None, limit=10, offset=0)
    completed_only = service.list_runs(current_user=current_user, status="completed", limit=10, offset=0)

    assert listed.total == 2
    assert len(listed.items) == 2
    listed_by_id = {item.id: item for item in listed.items}
    assert listed_by_id[UUID(str(first_run.id))].summary.keyword_count >= 1
    assert listed_by_id[UUID(str(first_run.id))].summary.opportunity_count >= 1
    assert listed_by_id[UUID(str(first_run.id))].depth_score is not None
    assert listed_by_id[UUID(str(first_run.id))].depth_score.score > 0.0
    no_evidence_item = next(item for item in listed.items if getattr(item.status, "value", item.status) == "completed_no_evidence")
    assert no_evidence_item.summary.keyword_count == 0
    assert no_evidence_item.summary.opportunity_count == 0
    assert no_evidence_item.depth_score is not None
    assert no_evidence_item.depth_score.score == 0.0
    assert completed_only.total == 1
    assert len(completed_only.items) == 1
    assert completed_only.items[0].id == first_run.id


def test_list_run_exports_returns_paginated_items_with_stable_total(
    session_factory,
    workspace,
    current_user: CurrentUser,
) -> None:
    run = _create_run(
        session_factory=session_factory,
        workspace=workspace,
        current_user=current_user,
        batch=make_batch(),
        seed_niche="romance",
    )
    run_id = UUID(str(run.id))
    export_service = ExportService(session_factory, export_storage_path=str(workspace / "exports"))

    first_export = export_service.create_export(
        current_user=current_user,
        run_id=run_id,
        payload=CreateExportRequest(format="json", scope="full_run"),
    )
    second_export = export_service.create_export(
        current_user=current_user,
        run_id=run_id,
        payload=CreateExportRequest(format="csv", scope="full_run"),
    )

    listed = export_service.list_run_exports(current_user=current_user, run_id=run_id, limit=1, offset=0)

    assert listed.total == 2
    assert len(listed.items) == 1
    assert listed.items[0].id in {first_export.id, second_export.id}
