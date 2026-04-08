"""Repository queries for exports."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.db.models import Export, ExportStatus
from app.db.repositories import PageResult


@dataclass(slots=True)
class RunExportListFilters:
    """Supported filters for listing exports within a run."""

    status: ExportStatus | None = None
    created_after: datetime | None = None
    created_before: datetime | None = None
    limit: int = 50
    offset: int = 0


class ExportRepository:
    """Thin persistence access for export entities."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        *,
        run_id: UUID,
        export_format: str,
        storage_uri: str | None = None,
        status: ExportStatus = ExportStatus.PENDING,
    ) -> Export:
        """Create and flush an export record."""
        export = Export(
            run_id=run_id,
            export_format=export_format,
            storage_uri=storage_uri,
            status=status,
        )
        self.session.add(export)
        self.session.flush()
        self.session.refresh(export)
        return export

    def get_by_id(self, export_id: UUID) -> Export | None:
        """Return an export by primary key."""
        statement = select(Export).where(Export.id == export_id)
        return self.session.scalar(statement)

    def list_for_run(
        self,
        *,
        run_id: UUID,
        filters: RunExportListFilters | None = None,
    ) -> PageResult[Export]:
        """List exports for a research run."""
        filters = filters or RunExportListFilters()
        statement = select(Export).where(Export.run_id == run_id)
        count_statement = select(func.count()).select_from(Export).where(Export.run_id == run_id)

        statement, count_statement = self._apply_filters(statement, count_statement, filters)
        statement = statement.order_by(Export.created_at.desc()).limit(filters.limit).offset(filters.offset)

        items = list(self.session.scalars(statement))
        total = self.session.scalar(count_statement) or 0
        return PageResult(items=items, total=total, limit=filters.limit, offset=filters.offset)

    @staticmethod
    def _apply_filters(
        statement: Select[tuple[Export]],
        count_statement: Select[tuple[int]],
        filters: RunExportListFilters,
    ) -> tuple[Select[tuple[Export]], Select[tuple[int]]]:
        """Apply list filters to both export query statements."""
        if filters.status is not None:
            statement = statement.where(Export.status == filters.status)
            count_statement = count_statement.where(Export.status == filters.status)
        if filters.created_after is not None:
            statement = statement.where(Export.created_at >= filters.created_after)
            count_statement = count_statement.where(Export.created_at >= filters.created_after)
        if filters.created_before is not None:
            statement = statement.where(Export.created_at <= filters.created_before)
            count_statement = count_statement.where(Export.created_at <= filters.created_before)
        return statement, count_statement

