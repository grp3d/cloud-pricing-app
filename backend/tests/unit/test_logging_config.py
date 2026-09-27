"""The log record pipeline (017-structured-json-logging, FR-001–FR-005, FR-011;
contracts/log-format.md §1): every record, from structlog or plain `logging`, is one JSON line
with `timestamp`, `level` and `message`."""

from __future__ import annotations

import io
import json
import logging
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest

from src.logging_config import configure_logging, get_logger


def _configure(level: str = "INFO", fmt: str = "json") -> io.StringIO:
    stream = io.StringIO()
    configure_logging(level=level, fmt=fmt, stream=stream)
    return stream


def _records(stream: io.StringIO) -> list[dict]:
    return [json.loads(line) for line in stream.getvalue().splitlines()]


def test_record_has_timestamp_level_message_and_fields():
    stream = _configure()
    get_logger("cloud_pricing.test").info("hello", sku="ABC")

    [record] = _records(stream)
    assert record["message"] == "hello"
    assert record["level"] == "info"
    assert record["sku"] == "ABC"
    assert record["logger"] == "cloud_pricing.test"
    assert "event" not in record
    assert record["timestamp"].endswith("+00:00")
    assert datetime.fromisoformat(record["timestamp"]).utcoffset() == timedelta(0)


def test_records_below_the_level_are_not_written():
    stream = _configure(level="INFO")
    get_logger("cloud_pricing.test").debug("hidden")
    assert stream.getvalue() == ""

    stream = _configure(level="WARNING")
    get_logger("cloud_pricing.test").info("hidden")
    assert stream.getvalue() == ""


def test_awkward_message_text_stays_one_line():
    stream = _configure()
    text = 'say "hi"\nnext line — é'
    get_logger("cloud_pricing.test").info(text)

    lines = stream.getvalue().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["message"] == text


class _Opaque:
    def __str__(self) -> str:
        return "opaque-thing"


def test_non_json_values_are_written_as_text():
    stream = _configure()
    an_id = uuid.uuid4()
    get_logger("cloud_pricing.test").info(
        "values", day=date(2026, 9, 26), an_id=an_id, amount=Decimal("1.50"), thing=_Opaque()
    )

    [record] = _records(stream)
    assert record["day"] == "2026-09-26"
    assert record["an_id"] == str(an_id)
    assert record["amount"] == "1.50"
    assert record["thing"] == "opaque-thing"


def test_configuring_twice_leaves_one_handler():
    _configure()
    stream = _configure()
    assert len(logging.getLogger().handlers) == 1

    get_logger("cloud_pricing.test").info("once")
    assert len(stream.getvalue().splitlines()) == 1


# --- US1: tracebacks, stdlib/Uvicorn records, console format ---------------------------------


def test_traceback_stays_inside_one_record():
    stream = _configure()
    try:
        1 / 0  # noqa: B018
    except ZeroDivisionError:
        get_logger("cloud_pricing.test").exception("boom")

    lines = stream.getvalue().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["level"] == "error"
    assert "Traceback" in record["exception"]
    assert "ZeroDivisionError" in record["exception"]


def test_stdlib_record_has_the_same_shape():
    stream = _configure()
    logging.getLogger("uvicorn.error").info("Started server process [%d]", 123)
    logging.getLogger("uvicorn.error").info("x", extra={"color_message": "\x1b[1mx\x1b[0m"})

    started, colored = _records(stream)
    assert started["message"] == "Started server process [123]"
    assert started["level"] == "info"
    assert started["logger"] == "uvicorn.error"
    assert datetime.fromisoformat(started["timestamp"]).utcoffset() == timedelta(0)
    assert "color_message" not in colored


def test_uvicorn_loggers_propagate_to_the_json_handler():
    for name in ("uvicorn", "uvicorn.access"):
        uv_logger = logging.getLogger(name)
        uv_logger.addHandler(logging.StreamHandler(io.StringIO()))
        uv_logger.propagate = False

    _configure()

    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uv_logger = logging.getLogger(name)
        assert uv_logger.handlers == []
        assert uv_logger.propagate is True
    assert logging.getLogger("uvicorn.access").level == logging.WARNING


def test_console_format_is_readable_not_json():
    stream = _configure(fmt="console")
    get_logger("x").info("hello", sku="ABC")

    line = stream.getvalue().strip()
    assert "hello" in line
    assert "ABC" in line
    with pytest.raises(json.JSONDecodeError):
        json.loads(line)


@pytest.fixture(autouse=True)
def _restore_logging():
    yield
    from src.config import settings

    configure_logging(settings.log_level, settings.log_format)
