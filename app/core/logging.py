"""Structured logging utilities for the application."""

from __future__ import annotations

import contextvars
import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

request_id_context: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_id",
    default=None,
)

_RESERVED_LOG_RECORD_FIELDS = {
    "args",
    "asctime",
    "created",
    "exc_info",
    "exc_text",
    "filename",
    "funcName",
    "levelname",
    "levelno",
    "lineno",
    "module",
    "msecs",
    "message",
    "msg",
    "name",
    "pathname",
    "process",
    "processName",
    "request_id",
    "relativeCreated",
    "stack_info",
    "taskName",
    "thread",
    "threadName",
}


class RequestContextFilter(logging.Filter):
    """Attach correlation-friendly context to log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not getattr(record, "request_id", None):
            record.request_id = get_request_id()
        return True


class JsonFormatter(logging.Formatter):
    """Render log records as JSON strings."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", None),
        }

        extra_fields = {
            key: value
            for key, value in record.__dict__.items()
            if key not in _RESERVED_LOG_RECORD_FIELDS and not key.startswith("_")
        }
        if extra_fields:
            record_details = extra_fields.pop("details", {})
            payload["details"] = dict(record_details) if isinstance(record_details, dict) else {"details": record_details}
            payload["details"].update(extra_fields)

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = self.formatStack(record.stack_info)

        return json.dumps(payload, default=str)


def setup_logging(log_level: str) -> None:
    """Configure application logging once for JSON-friendly output."""
    root_logger = logging.getLogger()
    normalized_level = log_level.upper()

    if getattr(root_logger, "_ebook_logging_configured", False):
        root_logger.setLevel(normalized_level)
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RequestContextFilter())

    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(normalized_level)
    root_logger._ebook_logging_configured = True

    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(logger_name)
        logger.handlers.clear()
        logger.propagate = True


def set_request_id(request_id: str) -> contextvars.Token[str | None]:
    """Store the request identifier in context-local storage."""
    return request_id_context.set(request_id)


def reset_request_id(token: contextvars.Token[str | None]) -> None:
    """Reset the request identifier to its prior value."""
    request_id_context.reset(token)


def get_request_id() -> str | None:
    """Return the active request identifier, if one is set."""
    return request_id_context.get()
