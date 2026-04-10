from __future__ import annotations

import sys
from uuid import UUID

from app.core.config import get_settings
from app.db.session import create_engine_from_url, create_session_factory
from app.services.html_report_service import HtmlReportService


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python generate_html_report.py <run_id>")
        return 1

    run_id = UUID(sys.argv[1])
    settings = get_settings()
    engine = create_engine_from_url(settings.database_url)
    session_factory = create_session_factory(engine)
    service = HtmlReportService(
        session_factory,
        export_storage_path=settings.export_storage_path,
    )
    output_path = service.generate_report(run_id=run_id)
    print(str(output_path.resolve()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
