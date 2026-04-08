from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.config import Settings
from app.db.models import SourceItem
from app.main import create_app


def build_test_client(workspace: Path) -> TestClient:
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
    return TestClient(create_app(settings=settings))


def make_workspace() -> Path:
    workspace = Path.cwd() / ".test-artifacts" / str(uuid4())
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace


def test_romance_research_flow_persists_results() -> None:
    client = build_test_client(make_workspace())

    create_response = client.post(
        "/api/v1/research-runs",
        json={"seed_niche": "romance", "config": {"max_candidates": 20, "top_k": 8}},
    )
    assert create_response.status_code == 201
    create_payload = create_response.json()
    assert create_payload["data"]["seed_niche"] == "romance"
    assert create_payload["data"]["status"] == "completed"

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

    assert run_payload["summary"]["keyword_count"] >= 5
    assert run_payload["summary"]["opportunity_count"] >= 5
    assert len(keyword_items) >= 5
    assert len(opportunity_items) >= 5
    assert progress_payload["status"] == "completed"
    assert progress_payload["percent_complete"] == 100.0

    with client.app.state.session_factory() as session:
        source_item_count = session.scalar(
            select(func.count()).select_from(SourceItem).where(SourceItem.run_id == UUID(run_id))
        )
    assert source_item_count is not None
    assert source_item_count >= 0


def test_export_generation_creates_file() -> None:
    client = build_test_client(make_workspace())

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
    assert len(exported_data[0]["keywords"]) >= 1
    assert isinstance(exported_data[0]["niche_summaries"], list)
