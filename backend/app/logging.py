"""Structured JSON logging (see ADR 0007).

Every log line is a single JSON object on stdout. PII is redacted at the
formatter level as a last-line defence; call sites should not put PII into
logs in the first place.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

from pythonjsonlogger.json import JsonFormatter

from app.config import get_settings

_REDACT_KEYS = {
    "password",
    "authorization",
    "cookie",
    "session",
    "token",
    "id_token",
    "access_token",
    "refresh_token",
    "service_account_json",
    "google_credentials",
}


class RedactingFormatter(JsonFormatter):
    def add_fields(
        self,
        log_record: dict[str, Any],
        record: logging.LogRecord,
        message_dict: dict[str, Any],
    ) -> None:
        super().add_fields(log_record, record, message_dict)
        for key in list(log_record.keys()):
            if key.lower() in _REDACT_KEYS:
                log_record[key] = "[REDACTED]"


_HANDLER_MARK = "_symphony_ta_handler"


def configure_logging() -> None:
    root = logging.getLogger()
    if any(getattr(h, _HANDLER_MARK, False) for h in root.handlers):
        return

    settings = get_settings()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        RedactingFormatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s",
            rename_fields={"asctime": "timestamp", "levelname": "level"},
        ),
    )
    setattr(handler, _HANDLER_MARK, True)

    root.handlers[:] = [handler]
    root.setLevel(settings.log_level.upper())


def get_logger(name: str) -> logging.Logger:
    configure_logging()
    return logging.getLogger(name)
