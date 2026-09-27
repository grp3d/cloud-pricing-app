"""The per-request log record (017-structured-json-logging, FR-006; contracts/log-format.md §2):
one `request completed` record per request, with the path only, never the query string."""

from __future__ import annotations

import re

import pytest

from src import config as config_module
from src.config import settings
from src.logging_config import get_logger


def _completed(records: list[dict]) -> list[dict]:
    return [r for r in records if r["message"] == "request completed"]


def _server(records: list[dict]) -> list[dict]:
    """Drop the test client's own `httpx` records (they log the full request URL)."""
    return [r for r in records if not r.get("logger", "").startswith(("httpx", "httpcore"))]


@pytest.mark.asyncio
async def test_request_completed_record(client, log_output):
    resp = await client.get("/health")
    assert resp.status_code == 200

    [record] = _completed(log_output())
    assert record["method"] == "GET"
    assert record["path"] == "/health"
    assert record["status_code"] == 200
    assert isinstance(record["duration_ms"], float)
    assert record["duration_ms"] >= 0
    assert record["logger"] == "cloud_pricing"


@pytest.mark.asyncio
async def test_not_found_is_logged_with_its_status(client, log_output):
    await client.get("/does-not-exist")

    [record] = _completed(log_output())
    assert record["status_code"] == 404


@pytest.mark.asyncio
async def test_query_string_is_never_logged(client, log_output):
    await client.get("/health", params={"token": "s3cr3t"})

    records = _server(log_output())
    [record] = _completed(records)
    assert record["path"] == "/health"
    assert all("s3cr3t" not in str(r) for r in records)


# --- US2: request IDs (FR-006a/b, contracts/log-format.md §3) --------------------------------

HEX_ID = re.compile(r"[0-9a-f]{32}")


@pytest.mark.asyncio
async def test_response_carries_the_records_request_id(client, log_output):
    first = await client.get("/health")
    second = await client.get("/health")

    ids = [first.headers["X-Request-ID"], second.headers["X-Request-ID"]]
    assert all(HEX_ID.fullmatch(i) for i in ids)
    assert ids[0] != ids[1]
    assert [r["request_id"] for r in _completed(log_output())] == ids


@pytest.mark.asyncio
async def test_valid_client_request_id_is_recorded_not_echoed(client, log_output):
    resp = await client.get("/health", headers={"X-Request-ID": "abc-123"})

    [record] = _completed(log_output())
    assert record["client_request_id"] == "abc-123"
    assert resp.headers["X-Request-ID"] != "abc-123"
    assert HEX_ID.fullmatch(resp.headers["X-Request-ID"])
    assert record["request_id"] == resp.headers["X-Request-ID"]


@pytest.mark.asyncio
@pytest.mark.parametrize("value", ["x" * 129, "caf\xe9".encode("latin-1")])
async def test_invalid_client_request_id_is_ignored(client, log_output, value):
    resp = await client.get("/health", headers={"X-Request-ID": value})

    assert resp.status_code == 200
    [record] = _completed(log_output())
    assert "client_request_id" not in record


@pytest.mark.asyncio
async def test_request_id_header_is_exposed_to_browsers(client):
    resp = await client.get("/health", headers={"Origin": settings.cors_allowed_origins[0]})

    assert "x-request-id" in resp.headers["access-control-expose-headers"].lower()


@pytest.mark.asyncio
async def test_error_inside_a_request_carries_its_request_id(
    client, auth_headers, log_output, monkeypatch, tmp_path
):
    monkeypatch.setattr(
        config_module.settings, "aws_pricing_parquet_dir", str(tmp_path / "missing")
    )
    resp = await client.get(
        "/api/v1/catalog/skus",
        params={"service_code": "AmazonEC2", "region": "us-east-1"},
        headers=auth_headers,
    )
    assert resp.status_code == 503

    records = log_output()
    [error] = [r for r in records if r["message"] == "pricing data unavailable"]
    assert error["level"] == "error"
    assert error["path"] == "/api/v1/catalog/skus"
    assert error["error"]
    [completed] = _completed(records)
    assert error["request_id"] == completed["request_id"] == resp.headers["X-Request-ID"]


def test_records_outside_a_request_have_no_request_id(log_output):
    get_logger("cloud_pricing").info("x")

    [record] = log_output()
    assert "request_id" not in record
