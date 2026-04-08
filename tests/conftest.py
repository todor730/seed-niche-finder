from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from app.api.dependencies import CurrentUser
from app.core.config import Settings
from app.db.base import Base
from app.db.session import create_engine_from_url, create_session_factory


def make_workspace() -> Path:
    workspace = Path.cwd() / ".test-artifacts" / str(uuid4())
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace


@pytest.fixture
def workspace() -> Path:
    return make_workspace()


@pytest.fixture
def app_settings(workspace: Path) -> Settings:
    return Settings(
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


@pytest.fixture
def engine(app_settings: Settings):
    engine = create_engine_from_url(app_settings.database_url)
    Base.metadata.create_all(bind=engine)
    return engine


@pytest.fixture
def session_factory(engine):
    return create_session_factory(engine)


@pytest.fixture
def current_user() -> CurrentUser:
    return CurrentUser()
