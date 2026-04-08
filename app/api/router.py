"""Top-level API router registration."""

from __future__ import annotations

from importlib import import_module

from fastapi import APIRouter


def _load_router(module_path: str, *, prefix: str = "", tags: list[str] | None = None) -> APIRouter:
    """Load a route module router or fall back to an empty placeholder router."""
    try:
        module = import_module(module_path)
    except ModuleNotFoundError as exc:
        if exc.name != module_path:
            raise
        return APIRouter(prefix=prefix, tags=tags or [])

    router = getattr(module, "router", None)
    if not isinstance(router, APIRouter):
        raise TypeError(f"{module_path} must expose an APIRouter named 'router'.")
    return router


health_router = _load_router("app.api.routes.health", tags=["health"])
research_runs_router = _load_router("app.api.routes.research_runs", tags=["research_runs"])
keywords_router = _load_router("app.api.routes.keywords", tags=["keywords"])
opportunities_router = _load_router("app.api.routes.opportunities", tags=["opportunities"])
exports_router = _load_router("app.api.routes.exports", tags=["exports"])

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(research_runs_router)
api_router.include_router(keywords_router)
api_router.include_router(opportunities_router)
api_router.include_router(exports_router)
