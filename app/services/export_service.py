"""Export service that materializes local files from persisted research data."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID, uuid4

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload, sessionmaker

from app.api.dependencies import CurrentUser
from app.core.errors import ExportNotFoundError, RunNotFoundError
from app.db.models import Export, ExportStatus, ResearchRun, ResearchRunStatus
from app.schemas.export import CreateExportRequest
from app.services.shared import ListResult, resolve_user_id, to_export_resource, to_keyword_list_item, to_opportunity_list_item
from app.services.summary_service import SummaryService


class ExportService:
    """Create and read persisted export records plus local export files."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        export_storage_path: str,
        summary_service: SummaryService | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._export_storage_path = Path(export_storage_path)
        self._export_storage_path.mkdir(parents=True, exist_ok=True)
        self._summary_service = summary_service or SummaryService()

    def create_export(self, *, current_user: CurrentUser, run_id: UUID, payload: CreateExportRequest):
        """Generate an export file immediately and persist its metadata."""
        with self._session_factory() as session:
            run = session.scalar(
                select(ResearchRun)
                .where(ResearchRun.id == run_id, ResearchRun.user_id == resolve_user_id(current_user))
                .options(
                    selectinload(ResearchRun.keyword_candidates),
                    selectinload(ResearchRun.opportunities),
                )
            )
            if run is None:
                raise RunNotFoundError(str(run_id))

            export_format = payload.format.value if hasattr(payload.format, "value") else str(payload.format)
            export_scope = payload.scope.value if hasattr(payload.scope, "value") else str(payload.scope)
            file_name = f"{run.seed_niche.replace(' ', '-')}-{export_scope}.{export_format}"
            file_path = self._export_storage_path / file_name
            payload_for_export = self._build_export_payload(
                session=session,
                run=run,
                export_scope=export_scope,
                export_format=export_format,
            )
            self._write_export(file_path, export_format, payload_for_export)

            export = Export(
                id=uuid4(),
                run_id=run_id,
                export_format=export_format,
                scope=export_scope,
                status=ExportStatus.COMPLETED,
                file_name=file_name,
                storage_uri=str(file_path.resolve()),
                download_url=None,
            )
            session.add(export)
            session.commit()
            session.refresh(export)
            return to_export_resource(export)

    def list_run_exports(self, *, current_user: CurrentUser, run_id: UUID, limit: int, offset: int) -> ListResult:
        """List persisted export records for a run."""
        with self._session_factory() as session:
            run = session.scalar(select(ResearchRun).where(ResearchRun.id == run_id, ResearchRun.user_id == resolve_user_id(current_user)))
            if run is None:
                raise RunNotFoundError(str(run_id))

            exports = list(
                session.scalars(
                    select(Export).where(Export.run_id == run_id).order_by(Export.created_at.desc()).limit(limit).offset(offset)
                )
            )
            total = len(list(session.scalars(select(Export).where(Export.run_id == run_id))))
            return ListResult(items=[to_export_resource(export) for export in exports], total=total, limit=limit, offset=offset)

    def get_export(self, *, current_user: CurrentUser, export_id: UUID):
        """Return a single persisted export record."""
        with self._session_factory() as session:
            statement = select(Export).where(Export.id == export_id).options(selectinload(Export.research_run))
            export = session.scalar(statement)
            if export is None or export.research_run.user_id != resolve_user_id(current_user):
                raise ExportNotFoundError(str(export_id))
            return to_export_resource(export)

    def _build_export_payload(
        self,
        *,
        session: Session,
        run: ResearchRun,
        export_scope: str,
        export_format: str,
    ) -> list[dict[str, object]] | dict[str, list[dict[str, object]]]:
        """Build export payloads in shapes that fit each target format."""
        keyword_records = [item.model_dump(mode="json") for item in map(to_keyword_list_item, run.keyword_candidates)]
        opportunity_records = [item.model_dump(mode="json") for item in map(to_opportunity_list_item, run.opportunities)]
        summary_report = self._summary_service.build_run_summary_report(session=session, run_id=run.id)
        niche_summary_records = [item.model_dump(mode="json") for item in summary_report.top_niche_opportunities]
        niche_summary_rows = self._summary_service.build_export_rows(report=summary_report)

        if export_scope == "keywords":
            return keyword_records
        if export_scope == "opportunities":
            return opportunity_records
        insufficient_evidence = run.status == ResearchRunStatus.COMPLETED_NO_EVIDENCE
        note = run.error_message or "Research completed without sufficient persisted evidence to support niche claims."
        if export_format == "xlsx":
            return {
                "run_overview": [
                    {
                        "run_id": str(run.id),
                        "seed_niche": run.seed_niche,
                        "status": run.status.value,
                        "generated_at": summary_report.generated_at.isoformat(),
                        "insufficient_evidence": insufficient_evidence,
                        "note": note if insufficient_evidence else "",
                    }
                ],
                "niche_summaries": niche_summary_rows,
                "keywords": keyword_records,
                "opportunities": opportunity_records,
            }
        if export_format == "csv":
            if insufficient_evidence and not niche_summary_rows:
                return [
                    {
                        "run_id": str(run.id),
                        "seed_niche": run.seed_niche,
                        "status": run.status.value,
                        "generated_at": summary_report.generated_at.isoformat(),
                        "insufficient_evidence": True,
                        "note": note,
                    }
                ]
            return niche_summary_rows
        return [
            {
                "run_id": str(run.id),
                "seed_niche": run.seed_niche,
                "status": run.status.value,
                "generated_at": summary_report.generated_at.isoformat(),
                "insufficient_evidence": insufficient_evidence,
                "notes": [note] if insufficient_evidence else [],
                "niche_summaries": niche_summary_records,
                "keywords": keyword_records,
                "opportunities": opportunity_records,
            }
        ]

    def _write_export(
        self,
        file_path: Path,
        export_format: str,
        payload: list[dict[str, object]] | dict[str, list[dict[str, object]]],
    ) -> None:
        """Write the export records to disk in the requested format."""
        if export_format == "json":
            file_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            return

        if export_format == "csv":
            records = payload if isinstance(payload, list) else payload.get("niche_summaries", [])
            dataframe = pd.json_normalize(records)
            dataframe.to_csv(file_path, index=False)
            return
        with pd.ExcelWriter(file_path) as writer:
            if isinstance(payload, dict):
                for sheet_name, rows in payload.items():
                    pd.json_normalize(rows).to_excel(writer, sheet_name=sheet_name[:31], index=False)
                return
            pd.json_normalize(payload).to_excel(writer, sheet_name="export", index=False)
