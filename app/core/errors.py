"""Application error types and exception handlers."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from enum import StrEnum
from typing import Any

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.logging import get_request_id
from app.schemas.common import ErrorEnvelope, ErrorObject

logger = logging.getLogger(__name__)


class ErrorCode(StrEnum):
    """Stable application error codes."""

    VALIDATION_ERROR = "VALIDATION_ERROR"
    INVALID_QUERY_PARAM = "INVALID_QUERY_PARAM"
    RUN_NOT_FOUND = "RUN_NOT_FOUND"
    KEYWORD_NOT_FOUND = "KEYWORD_NOT_FOUND"
    OPPORTUNITY_NOT_FOUND = "OPPORTUNITY_NOT_FOUND"
    EXPORT_NOT_FOUND = "EXPORT_NOT_FOUND"
    RATE_LIMITED = "RATE_LIMITED"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    PROVIDER_FAILURE = "PROVIDER_FAILURE"
    SCORING_FAILURE = "SCORING_FAILURE"
    EXPORT_FAILURE = "EXPORT_FAILURE"
    RESOURCE_NOT_FOUND = "RESOURCE_NOT_FOUND"


class ApplicationError(Exception):
    """Base exception for known application errors."""

    def __init__(
        self,
        *,
        code: ErrorCode,
        message: str,
        status_code: int,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}


class InvalidQueryParamError(ApplicationError):
    """Raised when query parameters are invalid."""

    def __init__(self, *, details: dict[str, Any] | None = None, message: str = "Invalid query parameters.") -> None:
        super().__init__(
            code=ErrorCode.INVALID_QUERY_PARAM,
            message=message,
            status_code=status.HTTP_400_BAD_REQUEST,
            details=details,
        )


class ResourceNotFoundError(ApplicationError):
    """Raised when a named resource does not exist."""

    def __init__(
        self,
        *,
        code: ErrorCode,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            code=code,
            message=message,
            status_code=status.HTTP_404_NOT_FOUND,
            details=details,
        )


class RunNotFoundError(ResourceNotFoundError):
    """Raised when a research run cannot be found."""

    def __init__(self, run_id: str) -> None:
        super().__init__(
            code=ErrorCode.RUN_NOT_FOUND,
            message="Research run not found.",
            details={"run_id": run_id},
        )


class KeywordNotFoundError(ResourceNotFoundError):
    """Raised when a keyword cannot be found."""

    def __init__(self, keyword_id: str) -> None:
        super().__init__(
            code=ErrorCode.KEYWORD_NOT_FOUND,
            message="Keyword not found.",
            details={"keyword_id": keyword_id},
        )


class OpportunityNotFoundError(ResourceNotFoundError):
    """Raised when an opportunity cannot be found."""

    def __init__(self, opportunity_id: str) -> None:
        super().__init__(
            code=ErrorCode.OPPORTUNITY_NOT_FOUND,
            message="Opportunity not found.",
            details={"opportunity_id": opportunity_id},
        )


class ExportNotFoundError(ResourceNotFoundError):
    """Raised when an export cannot be found."""

    def __init__(self, export_id: str) -> None:
        super().__init__(
            code=ErrorCode.EXPORT_NOT_FOUND,
            message="Export not found.",
            details={"export_id": export_id},
        )


def create_error_envelope(
    *,
    code: ErrorCode,
    message: str,
    details: dict[str, Any] | None = None,
    request_id: str | None = None,
) -> ErrorEnvelope:
    """Build the standard API error envelope."""
    meta: dict[str, Any] = {}
    if request_id:
        meta["request_id"] = request_id

    return ErrorEnvelope(
        data=None,
        meta=meta,
        error=ErrorObject(
            code=code,
            message=message,
            details=details or {},
        ),
    )


def create_error_response(
    *,
    status_code: int,
    code: ErrorCode,
    message: str,
    details: dict[str, Any] | None = None,
    request_id: str | None = None,
) -> JSONResponse:
    """Return the standard JSON error response."""
    envelope = create_error_envelope(
        code=code,
        message=message,
        details=details,
        request_id=request_id,
    )
    headers = {"X-Request-ID": request_id} if request_id else None
    return JSONResponse(
        status_code=status_code,
        content=envelope.model_dump(mode="json"),
        headers=headers,
    )


def register_exception_handlers(application: FastAPI) -> None:
    """Register global exception handlers on the application."""

    @application.exception_handler(ApplicationError)
    async def handle_application_error(request: Request, exc: ApplicationError) -> JSONResponse:
        request_id = _resolve_request_id(request)
        logger.warning(
            "Application error handled.",
            extra={
                "request_id": request_id,
                "error_code": exc.code,
                "status_code": exc.status_code,
                "path": request.url.path,
                "details": exc.details,
            },
        )
        return create_error_response(
            status_code=exc.status_code,
            code=exc.code,
            message=exc.message,
            details=exc.details,
            request_id=request_id,
        )

    @application.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        request_id = _resolve_request_id(request)
        error_code = _determine_validation_code(exc)
        details = {"errors": exc.errors()}
        logger.warning(
            "Request validation failed.",
            extra={
                "request_id": request_id,
                "error_code": error_code,
                "status_code": status.HTTP_422_UNPROCESSABLE_ENTITY,
                "path": request.url.path,
                "details": details,
            },
        )
        return create_error_response(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code=error_code,
            message="Invalid query parameters." if error_code is ErrorCode.INVALID_QUERY_PARAM else "Request validation failed.",
            details=details,
            request_id=request_id,
        )

    @application.exception_handler(HTTPException)
    async def handle_http_exception(request: Request, exc: HTTPException) -> JSONResponse:
        request_id = _resolve_request_id(request)
        code, message, details = _map_http_exception(exc)
        logger.warning(
            "HTTP exception handled.",
            extra={
                "request_id": request_id,
                "error_code": code,
                "status_code": exc.status_code,
                "path": request.url.path,
                "details": details,
            },
        )
        return create_error_response(
            status_code=exc.status_code,
            code=code,
            message=message,
            details=details,
            request_id=request_id,
        )

    @application.exception_handler(Exception)
    async def handle_unexpected_exception(request: Request, exc: Exception) -> JSONResponse:
        request_id = _resolve_request_id(request)
        logger.exception(
            "Unhandled exception caught by global handler.",
            extra={
                "request_id": request_id,
                "error_code": ErrorCode.INTERNAL_ERROR,
                "status_code": status.HTTP_500_INTERNAL_SERVER_ERROR,
                "path": request.url.path,
            },
        )
        return create_error_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code=ErrorCode.INTERNAL_ERROR,
            message="An unexpected internal error occurred.",
            details={},
            request_id=request_id,
        )


def _resolve_request_id(request: Request) -> str | None:
    """Return the request identifier from request state or logging context."""
    return getattr(request.state, "request_id", None) or get_request_id()


def _determine_validation_code(exc: RequestValidationError) -> ErrorCode:
    """Map FastAPI validation errors into stable application codes."""
    errors = exc.errors()
    if errors and all(error.get("loc", [None])[0] == "query" for error in errors):
        return ErrorCode.INVALID_QUERY_PARAM
    return ErrorCode.VALIDATION_ERROR


def _map_http_exception(exc: HTTPException) -> tuple[ErrorCode, str, dict[str, Any]]:
    """Map FastAPI HTTP exceptions into the standard error contract."""
    if isinstance(exc.detail, Mapping):
        detail_dict = dict(exc.detail)
        raw_code = detail_dict.get("code")
        code = ErrorCode(raw_code) if raw_code in ErrorCode._value2member_map_ else _default_http_error_code(exc.status_code)
        message = str(detail_dict.get("message", "Request failed."))
        details = detail_dict.get("details")
        if not isinstance(details, dict):
            details = {"detail": detail_dict}
        return code, message, details

    message = str(exc.detail) if exc.detail else "Request failed."
    details = {"detail": exc.detail} if exc.detail is not None else {}
    return _default_http_error_code(exc.status_code), message, details


def _default_http_error_code(status_code: int) -> ErrorCode:
    """Return a fallback application code for plain HTTP exceptions."""
    if status_code == status.HTTP_400_BAD_REQUEST:
        return ErrorCode.INVALID_QUERY_PARAM
    if status_code == status.HTTP_404_NOT_FOUND:
        return ErrorCode.RESOURCE_NOT_FOUND
    if status_code == status.HTTP_429_TOO_MANY_REQUESTS:
        return ErrorCode.RATE_LIMITED
    if status_code < status.HTTP_500_INTERNAL_SERVER_ERROR:
        return ErrorCode.VALIDATION_ERROR
    return ErrorCode.INTERNAL_ERROR
