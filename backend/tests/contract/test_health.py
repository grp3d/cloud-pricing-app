"""`GET /health` (018-app-cloud-deployment, FR-028; contracts/admin-api.md): public, typed, and
reports the pricing state as a fixed phrase — never a path, a location or an exception."""

from __future__ import annotations

import pytest

from src.pricing_data import active_snapshot


@pytest.mark.asyncio
async def test_health_needs_no_auth_and_reports_pricing(client):
    active_snapshot.get_active_snapshot()  # the server's startup check
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "pricing": "ok", "pricing_reason": None}


@pytest.mark.asyncio
async def test_health_without_a_snapshot_is_unavailable_with_a_fixed_phrase(
    client, use_pricing_root, tmp_path
):
    (tmp_path / "aws" / "manifests").mkdir(parents=True)  # a root with nothing published
    use_pricing_root(tmp_path)
    body = (await client.get("/health")).json()
    assert body["status"] == "ok"
    assert body["pricing"] == "unavailable"
    assert body["pricing_reason"] == "no snapshot available"
    assert str(tmp_path) not in str(body)


@pytest.mark.asyncio
async def test_health_hides_source_errors(client, monkeypatch):
    state = active_snapshot.MonitorState(
        initialized=True,
        last_check_error="checking s3://secret-bucket failed: AccessDenied for arn:aws:iam::1:x",
    )
    monkeypatch.setattr(active_snapshot, "STATE", state)
    body = (await client.get("/health")).json()
    assert body["pricing"] == "unavailable"
    assert body["pricing_reason"] == "data source unreachable"
    assert "secret-bucket" not in str(body)


@pytest.mark.asyncio
async def test_health_before_the_first_check_says_so(client, monkeypatch):
    monkeypatch.setattr(active_snapshot, "STATE", active_snapshot.MonitorState())
    body = (await client.get("/health")).json()
    assert (body["pricing"], body["pricing_reason"]) == ("unavailable", "not checked yet")
