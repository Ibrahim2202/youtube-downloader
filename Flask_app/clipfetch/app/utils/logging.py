"""Structured logging with per-request context."""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone

from flask import g, has_request_context

_FIELDS = ("request_id", "job_id", "platform", "operation", "duration_ms", "result", "error_category")


class _ContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if not getattr(record, "request_id", None) and has_request_context():
            record.request_id = getattr(g, "request_id", None)
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in _FIELDS + ("detail",):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


class TextFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        extras = " ".join(f"{k}={getattr(record, k)}" for k in _FIELDS + ("detail",)
                          if getattr(record, k, None) is not None)
        base = f"{self.formatTime(record, '%H:%M:%S')} {record.levelname:<7} {record.getMessage()} {extras}"
        return base + ("\n" + self.formatException(record.exc_info) if record.exc_info else "")


def setup_logging(level: str, json_format: bool) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter() if json_format else TextFormatter())
    handler.addFilter(_ContextFilter())
    root = logging.getLogger("clipfetch")
    root.handlers[:] = [handler]
    root.setLevel(level)
    root.propagate = False


def log_event(logger: logging.Logger, level: int, message: str, **fields) -> None:
    """Log with structured fields (request_id, job_id, platform, operation, duration_ms, ...)."""
    logger.log(level, message, extra=fields)
