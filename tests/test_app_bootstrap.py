from __future__ import annotations

from unittest.mock import Mock

from app.core.config import Settings
from app.main import create_app


def _make_settings(workspace, *, app_env: str, database_url: str) -> Settings:
    return Settings(
        _env_file=None,
        APP_ENV=app_env,
        APP_HOST="127.0.0.1",
        APP_PORT=8000,
        DATABASE_URL=database_url,
        EXPORT_STORAGE_PATH=str(workspace / "exports"),
        SECRET_KEY="test-secret",
        REDIS_URL="redis://localhost:6379/0",
        CORS_ALLOWED_ORIGINS="http://localhost:3000",
        ENABLED_PROVIDERS="",
    )


def test_create_app_auto_creates_schema_only_for_local_dev_sqlite(workspace, monkeypatch) -> None:
    fake_engine = object()
    fake_session_factory = Mock()
    create_all_mock = Mock()

    monkeypatch.setattr("app.main.create_engine_from_url", lambda url: fake_engine)
    monkeypatch.setattr("app.main.create_session_factory", lambda engine: fake_session_factory)
    monkeypatch.setattr("app.main.build_enabled_providers", lambda names: [])
    monkeypatch.setattr("app.main.Base.metadata.create_all", create_all_mock)

    settings = _make_settings(workspace, app_env="dev", database_url=f"sqlite:///{(workspace / 'dev.db').as_posix()}")
    app = create_app(settings=settings)

    assert app.state.settings.should_auto_create_schema is True
    create_all_mock.assert_called_once_with(bind=fake_engine)


def test_create_app_does_not_auto_create_schema_outside_local_dev(workspace, monkeypatch) -> None:
    fake_engine = object()
    fake_session_factory = Mock()
    create_all_mock = Mock()

    monkeypatch.setattr("app.main.create_engine_from_url", lambda url: fake_engine)
    monkeypatch.setattr("app.main.create_session_factory", lambda engine: fake_session_factory)
    monkeypatch.setattr("app.main.build_enabled_providers", lambda names: [])
    monkeypatch.setattr("app.main.Base.metadata.create_all", create_all_mock)

    settings = _make_settings(workspace, app_env="prod", database_url="postgresql://user:pass@localhost:5432/app")
    app = create_app(settings=settings)

    assert app.state.settings.should_auto_create_schema is False
    create_all_mock.assert_not_called()
