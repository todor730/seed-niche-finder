"""Reusable FastAPI dependencies for API routes."""

from __future__ import annotations

from collections.abc import Generator
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from fastapi import Request
from sqlalchemy.orm import Session

from app.db.session import get_db_session


@dataclass(slots=True)
class CurrentUser:
    """Placeholder authenticated user context."""

    id: UUID | None = None
    email: str | None = None
    is_authenticated: bool = False


class ServicePlaceholder:
    """Lightweight placeholder returned until a service is wired into app state."""

    def __init__(self, service_name: str) -> None:
        self.service_name = service_name

    def __getattr__(self, item: str) -> Any:
        raise RuntimeError(
            f"{self.service_name} is not configured yet. "
            f"Tried to access attribute '{item}'."
        )


def get_session(request: Request) -> Generator[Session, None, None]:
    """Yield a database session dependency."""
    session_factory = getattr(request.app.state, "session_factory", None)
    if session_factory is None:
        yield from get_db_session()
        return

    session = session_factory()
    try:
        yield session
    finally:
        session.close()


def get_current_user(request: Request) -> CurrentUser:
    """Return the current user context if middleware/auth sets one, otherwise an anonymous placeholder."""
    current_user = getattr(request.state, "current_user", None)
    if current_user is None:
        return CurrentUser()
    if isinstance(current_user, CurrentUser):
        return current_user
    if isinstance(current_user, dict):
        return CurrentUser(**current_user)
    return CurrentUser(
        id=getattr(current_user, "id", None),
        email=getattr(current_user, "email", None),
        is_authenticated=getattr(current_user, "is_authenticated", True),
    )


def get_research_service(request: Request) -> Any:
    """Return the research service placeholder or configured app service."""
    return getattr(request.app.state, "research_service", ServicePlaceholder("research_service"))


def get_keyword_service(request: Request) -> Any:
    """Return the keyword service placeholder or configured app service."""
    return getattr(request.app.state, "keyword_service", ServicePlaceholder("keyword_service"))


def get_opportunity_service(request: Request) -> Any:
    """Return the opportunity service placeholder or configured app service."""
    return getattr(request.app.state, "opportunity_service", ServicePlaceholder("opportunity_service"))


def get_export_service(request: Request) -> Any:
    """Return the export service placeholder or configured app service."""
    return getattr(request.app.state, "export_service", ServicePlaceholder("export_service"))
