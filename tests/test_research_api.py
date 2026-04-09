from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.config import Settings
from app.db.models import ResearchRunStatus
from app.db.models import SourceItem
from app.main import create_app
from app.schemas.research import CreateResearchRunRequest
from app.services.export_service import ExportService
from app.services.providers import ProviderSearchBatchResult
from app.services.research_service import ResearchService
from tests.test_research_service_evidence import FakeProviderRegistry, make_batch, make_empty_batch


def build_test_client(workspace: Path, *, batch: ProviderSearchBatchResult) -> TestClient:
    settings = Settings(
        _env_file=None,
        APP_ENV="dev",
        APP_HOST="127.0.0.1",
        APP_PORT=8000,
        DATABASE_URL=f"sqlite:///{(workspace / 'test.db').as_posix()}",
        EXPORT_STORAGE_PATH=str(workspace / "exports"),
        SECRET_KEY="test-secret",
        REDIS_URL="redis://localhost:6379/0",
        CORS_ALLOWED_ORIGINS="http://localhost:3000",
    )
    app = create_app(settings=settings)
    app.state.research_service = ResearchService(
        app.state.session_factory,
        export_storage_path=settings.export_storage_path,
        provider_registry=FakeProviderRegistry(batch),
    )
    app.state.export_service = ExportService(app.state.session_factory, export_storage_path=settings.export_storage_path)
    return TestClient(app)


def make_workspace() -> Path:
    workspace = Path.cwd() / ".test-artifacts" / str(uuid4())
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace


def test_romance_research_flow_persists_results() -> None:
    client = build_test_client(make_workspace(), batch=make_batch())

    create_response = client.post(
        "/api/v1/research-runs",
        json={"seed_niche": "romance", "config": {"max_candidates": 20, "top_k": 8}},
    )
    assert create_response.status_code == 201
    create_payload = create_response.json()
    assert create_payload["data"]["seed_niche"] == "romance"
    assert create_payload["data"]["status"] == "completed"
    assert create_payload["data"]["depth_score"]["score"] > 0.0

    run_id = create_payload["data"]["id"]

    run_response = client.get(f"/api/v1/research-runs/{run_id}")
    keywords_response = client.get(f"/api/v1/research-runs/{run_id}/keywords")
    opportunities_response = client.get(f"/api/v1/research-runs/{run_id}/opportunities")
    progress_response = client.get(f"/api/v1/research-runs/{run_id}/progress")

    assert run_response.status_code == 200
    assert keywords_response.status_code == 200
    assert opportunities_response.status_code == 200
    assert progress_response.status_code == 200

    run_payload = run_response.json()["data"]
    keyword_items = keywords_response.json()["data"]
    opportunity_items = opportunities_response.json()["data"]
    progress_payload = progress_response.json()["data"]

    assert run_payload["summary"]["keyword_count"] >= 1
    assert run_payload["summary"]["opportunity_count"] >= 1
    assert run_payload["depth_score"]["score"] > 0.0
    assert run_payload["depth_score"]["source_items_count"] >= 1
    assert len(keyword_items) >= 1
    assert len(opportunity_items) >= 1
    assert any("romance" in item["keyword_text"].lower() for item in keyword_items)
    assert any("romance" in item["title"].lower() for item in opportunity_items)
    assert progress_payload["status"] == "completed"
    assert progress_payload["percent_complete"] == 100.0

    with client.app.state.session_factory() as session:
        source_item_count = session.scalar(
            select(func.count()).select_from(SourceItem).where(SourceItem.run_id == UUID(run_id))
        )
    assert source_item_count is not None
    assert source_item_count >= 0


def test_export_generation_creates_file() -> None:
    client = build_test_client(make_workspace(), batch=make_batch())

    create_response = client.post(
        "/api/v1/research-runs",
        json={"seed_niche": "romance", "config": {"max_candidates": 20, "top_k": 5}},
    )
    run_id = create_response.json()["data"]["id"]

    export_response = client.post(
        f"/api/v1/research-runs/{run_id}/exports",
        json={"format": "json", "scope": "full_run"},
    )
    assert export_response.status_code == 201
    export_payload = export_response.json()["data"]

    export_path = Path(export_payload["storage_uri"])
    assert export_path.exists()

    exported_data = json.loads(export_path.read_text(encoding="utf-8"))
    assert exported_data[0]["seed_niche"] == "romance"
    assert exported_data[0]["depth_score"]["score"] > 0.0
    assert len(exported_data[0]["keywords"]) >= 1
    assert isinstance(exported_data[0]["niche_summaries"], list)


def test_zero_evidence_run_is_honest_in_api_and_export_payloads() -> None:
    client = build_test_client(make_workspace(), batch=make_empty_batch(include_failure=True))

    create_response = client.post(
        "/api/v1/research-runs",
        json={"seed_niche": "romance", "config": {"max_candidates": 20, "top_k": 5}},
    )
    assert create_response.status_code == 201
    create_payload = create_response.json()["data"]
    run_id = create_payload["id"]

    assert create_payload["status"] == ResearchRunStatus.COMPLETED_NO_EVIDENCE.value
    assert create_payload["error_message"] == "No persisted source evidence was collected from the configured providers."
    assert create_payload["depth_score"]["score"] == 0.0

    run_response = client.get(f"/api/v1/research-runs/{run_id}")
    progress_response = client.get(f"/api/v1/research-runs/{run_id}/progress")
    keywords_response = client.get(f"/api/v1/research-runs/{run_id}/keywords")
    opportunities_response = client.get(f"/api/v1/research-runs/{run_id}/opportunities")

    assert run_response.status_code == 200
    assert progress_response.status_code == 200
    assert keywords_response.status_code == 200
    assert opportunities_response.status_code == 200

    run_payload = run_response.json()["data"]
    progress_payload = progress_response.json()["data"]
    keyword_items = keywords_response.json()["data"]
    opportunity_items = opportunities_response.json()["data"]

    assert run_payload["status"] == ResearchRunStatus.COMPLETED_NO_EVIDENCE.value
    assert run_payload["depth_score"]["score"] == 0.0
    assert run_payload["summary"]["keyword_count"] == 0
    assert run_payload["summary"]["opportunity_count"] == 0
    assert progress_payload["status"] == ResearchRunStatus.COMPLETED_NO_EVIDENCE.value
    assert progress_payload["current_stage"] == "completed_no_evidence"
    assert progress_payload["percent_complete"] == 100.0
    assert "without sufficient persisted evidence" in progress_payload["message"]
    assert keyword_items == []
    assert opportunity_items == []

    export_response = client.post(
        f"/api/v1/research-runs/{run_id}/exports",
        json={"format": "json", "scope": "full_run"},
    )
    assert export_response.status_code == 201
    export_path = Path(export_response.json()["data"]["storage_uri"])
    exported_data = json.loads(export_path.read_text(encoding="utf-8"))

    assert exported_data[0]["status"] == ResearchRunStatus.COMPLETED_NO_EVIDENCE.value
    assert exported_data[0]["depth_score"]["score"] == 0.0
    assert exported_data[0]["insufficient_evidence"] is True
    assert exported_data[0]["keywords"] == []
    assert exported_data[0]["opportunities"] == []
    assert exported_data[0]["niche_summaries"] == []
    assert exported_data[0]["notes"] == ["No persisted source evidence was collected from the configured providers."]
