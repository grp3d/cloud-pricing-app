"""Structured JSON logging (017-structured-json-logging; contracts/log-format.md).

`configure_logging` installs one root handler whose structlog `ProcessorFormatter` renders every
record, from structlog loggers and plain `logging` loggers (Uvicorn, SQLAlchemy) alike, as one
JSON line with `timestamp` (ISO 8601, UTC), `level` and `message`, plus any detail fields.
`LOG_FORMAT=console` swaps the JSON renderer for readable, colored lines with the same fields.
"""

from __future__ import annotations

import logging
import sys
from datetime import UTC, datetime
from typing import Literal, TextIO

import structlog
from structlog.typing import EventDict, WrappedLogger


def _add_timestamp(_logger: WrappedLogger, _method: str, event_dict: EventDict) -> EventDict:
    # structlog's TimeStamper writes UTC as "Z"; the contract promises a "+00:00" offset.
    event_dict["timestamp"] = datetime.now(UTC).isoformat()
    return event_dict


def configure_logging(
    level: str, fmt: Literal["json", "console"], stream: TextIO = sys.stdout
) -> None:
    """(Re)configure all process logging. Idempotent: replaces the root handlers each call."""
    shared: list = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        _add_timestamp,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.EventRenamer("message"),
    ]
    renderer = (
        structlog.dev.ConsoleRenderer(colors=True, event_key="message")
        if fmt == "console"
        else structlog.processors.JSONRenderer(default=str)
    )

    handler = logging.StreamHandler(stream)
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=shared,
            processors=[structlog.stdlib.ProcessorFormatter.remove_processors_meta, renderer],
        )
    )
    root = logging.getLogger()
    for existing in list(root.handlers):
        root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(level.upper())

    # Uvicorn installs its own handlers with propagate=False, bypassing the root handler. Route its
    # records to the JSON handler instead, and quiet its access line: the app's own
    # `request completed` record replaces it (research.md §2).
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uv_logger = logging.getLogger(name)
        uv_logger.handlers.clear()
        uv_logger.propagate = True
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

    # The shared chain appears in both places on purpose: `foreign_pre_chain` runs only for plain
    # `logging` records, this chain only for structlog's own, so each record passes through once.
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            *shared,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=False,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
