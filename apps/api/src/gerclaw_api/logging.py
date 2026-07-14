"""Structured JSON logging with request context and PHI redaction."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from gerclaw_api.context import request_id_var, trace_id_var
from gerclaw_api.security import sanitize_payload

_RESERVED_LOG_RECORD_KEYS = frozenset(logging.makeLogRecord({}).__dict__)


class JsonFormatter(logging.Formatter):
    """Render one redacted JSON object per log record."""

    def format(self, record: logging.LogRecord) -> str:
        """Format the supplied record without leaking secrets or PHI."""

        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_var.get(),
            "trace_id": trace_id_var.get(),
        }
        extras = {
            key: value
            for key, value in record.__dict__.items()
            if key not in _RESERVED_LOG_RECORD_KEYS and not key.startswith("_")
        }
        if extras:
            payload["attributes"] = extras
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(sanitize_payload(payload), ensure_ascii=False, allow_nan=False)


def configure_logging(level: str) -> None:
    """Configure process-wide structured logging."""

    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(logger_name)
        logger.handlers.clear()
        logger.propagate = True
    logging.getLogger("uvicorn.access").disabled = True
    # Provider SDK INFO records commonly include full tenant-specific endpoints.
    # Keep safe GerClaw audit metadata while suppressing third-party request details.
    for logger_name in ("anthropic", "dashscope", "httpcore", "httpx", "openai"):
        logging.getLogger(logger_name).setLevel(logging.WARNING)
