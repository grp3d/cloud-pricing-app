"""Contract tests for `GET /admin/system-info` (016-canvas-icon-layout, US5,
contracts/api.md §1)."""

from __future__ import annotations

import pytest

from src.pricing_data import active_snapshot
from src.pricing_data.active_snapshot import Issue


@pytest.mark.asyncio
async def test_non_admin_is_rejected(client, auth_headers):
    resp = await client.get("/api/v1/admin/system-info", headers=auth_headers)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_gets_the_active_snapshot_and_status(client, admin_headers):
    expected = active_snapshot.get_active_snapshot_date()
    resp = await client.get("/api/v1/admin/system-info", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["active_snapshot_date"] == expected
    assert body["pinned"] is False
    assert body["last_check_at"] is not None
    interval = active_snapshot.settings.snapshot_check_interval_seconds
    assert body["check_interval_seconds"] == interval
    assert isinstance(body["waiting_snapshots"], list)
    assert isinstance(body["issues"], list)


@pytest.mark.asyncio
async def test_issues_come_back_in_the_documented_order(client, admin_headers, monkeypatch):
    active_snapshot.get_active_snapshot_date()
    issues = [
        Issue(
            kind="missing_icon",
            snapshot_date="2026-09-24",
            message="old",
            service_code="ZZB",
            service_name="B",
            is_new=False,
        ),
        Issue(
            kind="missing_icon",
            snapshot_date="2026-09-24",
            message="new",
            service_code="ZZA",
            service_name="A",
            is_new=True,
        ),
        Issue(
            kind="missing_regions",
            snapshot_date="2026-09-24",
            message="regions",
            regions=["eu-west-2"],
        ),
        Issue(kind="pinned_incomplete", snapshot_date="2026-09-24", message="pinned"),
    ]
    monkeypatch.setattr(active_snapshot.STATE, "issues", issues)
    resp = await client.get("/api/v1/admin/system-info", headers=admin_headers)
    kinds = [(i["kind"], i["service_code"]) for i in resp.json()["issues"]]
    assert kinds == [
        ("pinned_incomplete", None),
        ("missing_regions", None),
        ("missing_icon", "ZZA"),
        ("missing_icon", "ZZB"),
    ]
    regions_issue = resp.json()["issues"][1]
    assert regions_issue["regions"] == ["eu-west-2"]
