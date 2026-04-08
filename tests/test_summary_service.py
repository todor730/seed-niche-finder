from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

from app.api.dependencies import CurrentUser
from app.schemas.export import CreateExportRequest
from app.schemas.report import RunSummaryReport
from app.schemas.research import CreateResearchRunRequest
from app.services.export_service import ExportService
from app.services.research_service import ResearchService
from app.services.summary_service import SummaryService
from tests.test_research_service_evidence import FakeProviderRegistry, make_batch


def _create_ranked_run(session_factory, workspace: Path, current_user: CurrentUser) -> UUID:
    service = ResearchService(
        session_factory,
        export_storage_path=str(workspace / "exports"),
        provider_registry=FakeProviderRegistry(make_batch()),
    )
    created_run = service.create_run(
        current_user=current_user,
        payload=CreateResearchRunRequest(seed_niche="romance", config={"max_candidates": 20, "top_k": 5}),
    )
    return UUID(str(created_run.id))


def test_summary_service_builds_decision_grade_report(
    session_factory,
    workspace: Path,
    current_user: CurrentUser,
) -> None:
    run_id = _create_ranked_run(session_factory, workspace, current_user)
    summary_service = SummaryService()

    with session_factory() as session:
        report = summary_service.build_run_summary_report(session=session, run_id=run_id)

    assert isinstance(report, RunSummaryReport)
    assert report.run_id == run_id
    assert report.seed_niche == "romance"
    assert report.top_niche_opportunities

    top_summary = report.top_niche_opportunities[0]
    assert top_summary.niche_label
    assert top_summary.score_breakdown.final_score >= 0.0
    assert top_summary.source_agreement.source_count >= 1
    assert top_summary.source_agreement.evidence_count >= 1
    assert top_summary.key_signals
    assert top_summary.why_it_may_work
    assert top_summary.why_it_may_fail or top_summary.risk_flags
    assert top_summary.next_validation_queries
    assert "amazing" not in " ".join(top_summary.why_it_may_work).lower()
    assert top_summary.traceability["supporting_source_item_ids"]


def test_summary_service_export_rows_are_flat_and_export_ready(
    session_factory,
    workspace: Path,
    current_user: CurrentUser,
) -> None:
    run_id = _create_ranked_run(session_factory, workspace, current_user)
    summary_service = SummaryService()

    with session_factory() as session:
        report = summary_service.build_run_summary_report(session=session, run_id=run_id)
        rows = summary_service.build_export_rows(report=report)

    assert rows
    first_row = rows[0]
    assert first_row["run_id"] == str(run_id)
    assert first_row["seed_niche"] == "romance"
    assert isinstance(first_row["key_signals"], str)
    assert isinstance(first_row["why_it_may_work"], str)
    assert isinstance(first_row["risk_flags"], str)


def test_full_run_json_export_includes_niche_summaries(
    session_factory,
    workspace: Path,
    current_user: CurrentUser,
) -> None:
    run_id = _create_ranked_run(session_factory, workspace, current_user)
    export_service = ExportService(session_factory, export_storage_path=str(workspace / "exports"))

    export_resource = export_service.create_export(
        current_user=current_user,
        run_id=run_id,
        payload=CreateExportRequest(format="json", scope="full_run"),
    )

    export_path = Path(export_resource.storage_uri or "")
    exported_data = json.loads(export_path.read_text(encoding="utf-8"))

    assert exported_data
    assert exported_data[0]["seed_niche"] == "romance"
    assert exported_data[0]["niche_summaries"]
    first_summary = exported_data[0]["niche_summaries"][0]
    assert "niche_label" in first_summary
    assert "source_agreement" in first_summary
    assert "competition_density" in first_summary
    assert "next_validation_queries" in first_summary


def test_repeated_exports_create_distinct_immutable_artifacts(
    session_factory,
    workspace: Path,
    current_user: CurrentUser,
) -> None:
    run_id = _create_ranked_run(session_factory, workspace, current_user)
    export_service = ExportService(session_factory, export_storage_path=str(workspace / "exports"))

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
    assert first_export.file_name != second_export.file_name
    assert first_path != second_path
    assert first_path.exists()
    assert second_path.exists()
    assert first_path.read_text(encoding="utf-8")
    assert second_path.read_text(encoding="utf-8")
