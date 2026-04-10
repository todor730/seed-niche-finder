from __future__ import annotations

from pathlib import Path
from uuid import UUID

from app.api.dependencies import CurrentUser
from app.schemas.export import CreateExportRequest
from app.schemas.research import CreateResearchRunRequest
from app.services.export_service import ExportService
from app.services.html_report_service import HtmlReportService
from app.services.research_service import ResearchService
from tests.test_research_service_evidence import FakeProviderRegistry, make_batch, make_empty_batch


def _create_run(
    session_factory,
    workspace: Path,
    current_user: CurrentUser,
    *,
    seed_niche: str,
    provider_registry: FakeProviderRegistry,
) -> UUID:
    service = ResearchService(
        session_factory,
        export_storage_path=str(workspace / "exports"),
        provider_registry=provider_registry,
    )
    created_run = service.create_run(
        current_user=current_user,
        payload=CreateResearchRunRequest(seed_niche=seed_niche, config={"max_candidates": 20, "top_k": 10}),
    )
    return UUID(str(created_run.id))


def test_html_report_service_generates_browser_first_report_for_evidence_backed_run(
    session_factory,
    workspace: Path,
    current_user: CurrentUser,
) -> None:
    run_id = _create_run(
        session_factory,
        workspace,
        current_user,
        seed_niche="romance",
        provider_registry=FakeProviderRegistry(make_batch()),
    )
    export_service = ExportService(session_factory, export_storage_path=str(workspace / "exports"))
    export_resource = export_service.create_export(
        current_user=current_user,
        run_id=run_id,
        payload=CreateExportRequest(format="json", scope="full_run"),
    )
    report_service = HtmlReportService(session_factory, export_storage_path=str(workspace / "exports"))

    report_path = report_service.generate_report(run_id=run_id)
    html = report_path.read_text(encoding="utf-8")

    assert report_path.exists()
    assert report_path.suffix == ".html"
    assert f"{run_id}" in html
    assert "Decision Summary" in html
    assert "Run Health Snapshot" in html
    assert "Keywords" in html
    assert "Opportunities" in html
    assert "Warnings" in html
    assert "Confidence &amp; Missing Data" not in html
    assert "Confidence & Missing Data" in html
    assert "Diagnostics Summary" in html
    assert "Export / Artifacts" in html
    assert export_resource.file_name in html
    assert "No final opportunities were materialized" not in html


def test_html_report_service_handles_completed_no_evidence_runs_honestly(
    session_factory,
    workspace: Path,
    current_user: CurrentUser,
) -> None:
    run_id = _create_run(
        session_factory,
        workspace,
        current_user,
        seed_niche="self-help",
        provider_registry=FakeProviderRegistry(make_empty_batch(include_failure=True)),
    )
    report_service = HtmlReportService(session_factory, export_storage_path=str(workspace / "exports"))

    report_path = report_service.generate_report(run_id=run_id)
    html = report_path.read_text(encoding="utf-8")

    assert report_path.exists()
    assert "completed_no_evidence" in html
    assert "No evidence-backed opportunities were materialized for this run." in html
    assert "No final opportunities were materialized from the persisted evidence." in html
    assert "No final keywords were materialized." in html
    assert "No opportunities" in html
    assert "Export / Artifacts" in html
