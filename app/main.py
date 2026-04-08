"""FastAPI application bootstrap."""

from __future__ import annotations

import logging
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import Settings, get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import reset_request_id, set_request_id, setup_logging
from app.db import models  # noqa: F401
from app.db.base import Base
from app.db.session import create_engine_from_url, create_session_factory
from app.services.export_service import ExportService
from app.services.keyword_service import KeywordService
from app.services.opportunity_service import OpportunityService
from app.services.providers import ProviderRegistry, ProviderRequestPolicy, build_enabled_providers
from app.services.research_service import ResearchService

SERVICE_VERSION = "1.0.0"
logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure the FastAPI application instance."""
    app_settings = settings or get_settings()
    setup_logging(app_settings.log_level)
    engine = create_engine_from_url(app_settings.database_url)
    session_factory = create_session_factory(engine)
    provider_registry = ProviderRegistry(
        build_enabled_providers(app_settings.enabled_providers),
        request_policy=ProviderRequestPolicy(
            timeout_seconds=app_settings.provider_http_timeout_seconds,
            max_retries=app_settings.provider_http_max_retries,
            retry_backoff_seconds=app_settings.provider_http_retry_backoff_seconds,
            user_agent=app_settings.provider_user_agent,
        ),
    )
    Base.metadata.create_all(bind=engine)
    Path(app_settings.export_storage_path).mkdir(parents=True, exist_ok=True)

    application = FastAPI(
        title=app_settings.app_name,
        version=SERVICE_VERSION,
        description="Backend service for orchestrating ebook niche research runs.",
    )

    application.state.settings = app_settings
    application.state.engine = engine
    application.state.session_factory = session_factory
    application.state.provider_registry = provider_registry
    application.state.research_service = ResearchService(
        session_factory,
        export_storage_path=app_settings.export_storage_path,
        provider_registry=provider_registry,
    )
    application.state.keyword_service = KeywordService(session_factory)
    application.state.opportunity_service = OpportunityService(session_factory)
    application.state.export_service = ExportService(session_factory, export_storage_path=app_settings.export_storage_path)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=app_settings.cors_allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.include_router(api_router, prefix=app_settings.api_v1_prefix)
    register_exception_handlers(application)

    @application.middleware("http")
    async def add_request_context(request: Request, call_next) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid4())
        request.state.request_id = request_id
        token = set_request_id(request_id)
        started_at = perf_counter()
        response: Response | None = None

        try:
            response = await call_next(request)
        finally:
            duration_ms = round((perf_counter() - started_at) * 1000, 2)
            logger.info(
                "Request completed.",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "duration_ms": duration_ms,
                    "status_code": response.status_code if response is not None else 500,
                },
            )
            reset_request_id(token)

        response.headers["X-Request-ID"] = request_id
        return response

    logger.info(
        "Application configured.",
        extra={
            "app_env": app_settings.app_env,
            "host": app_settings.app_host,
            "port": app_settings.app_port,
            "api_prefix": app_settings.api_v1_prefix,
        },
    )
    return application


app = create_app()
