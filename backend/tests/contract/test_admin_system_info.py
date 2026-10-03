"""Contract tests for `GET /admin/system-info` (016-canvas-icon-layout, US5,
contracts/api.md §1; 018-app-cloud-deployment, FR-012, FR-014, contracts/admin-api.md)."""

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
    active = active_snapshot.get_active_snapshot()
    resp = await client.get("/api/v1/admin/system-info", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["deployment"] == {"environment": "local", "release": "dev"}
    assert body["source"]["kind"] == "local"
    assert body["source"]["provider"] == "aws"
    assert body["active"]["snapshot_date"] == active.snapshot_date
    assert body["active"]["revision"] == active.revision
    assert body["active"]["run_id"] == active.manifest.run_id
    assert body["active"]["pipeline_version"] == active.manifest.run.pipeline_version.image_tag
    assert body["active"]["pinned"] is False
    assert "us-east-1" in body["active"]["regions"]
    assert body["active"]["failed_regions"] == []
    assert body["latest_run"]["status"] == "succeeded"
    assert body["rejected"] is None
    assert body["cache"] is None  # a local source has no cache
    assert body["last_check_at"] is not None
    interval = active_snapshot.settings.snapshot_check_interval_seconds
    assert body["check_interval_seconds"] == interval
    assert isinstance(body["issues"], list)
    assert "waiting_snapshots" not in body
    assert "active_snapshot_date" not in body


@pytest.mark.asyncio
async def test_source_never_contains_credentials(client, admin_headers, monkeypatch):
    active_snapshot.get_active_snapshot()
    monkeypatch.setattr(active_snapshot.settings, "pricing_data_uri",
                        "s3://cloud-pricing-data-prod-x/some/prefix")
    body = (await client.get("/api/v1/admin/system-info", headers=admin_headers)).json()
    assert body["source"] == {"kind": "s3", "location": "s3://cloud-pricing-data-prod-x/some/prefix",
                              "provider": "aws"}


@pytest.mark.asyncio
async def test_a_rejected_manifest_and_a_partial_latest_run_are_shown(
    client, admin_headers, monkeypatch
):
    active_snapshot.get_active_snapshot()
    from src.pricing_data.manifest import FailedRegion, RejectedManifest

    monkeypatch.setattr(active_snapshot.STATE, "rejected",
                        RejectedManifest("2026-10-12", 1, "table price_fact schema version 2"))
    monkeypatch.setattr(active_snapshot.STATE, "latest_run", active_snapshot.LatestRun(
        "2026-10-12", 1, "partial", [FailedRegion(region="ap-northeast-1", reason="timeout",
                                                  attempts=3)]))
    body = (await client.get("/api/v1/admin/system-info", headers=admin_headers)).json()
    assert body["rejected"] == {"snapshot_date": "2026-10-12", "revision": 1,
                                "reason": "table price_fact schema version 2"}
    assert body["latest_run"]["status"] == "partial"
    assert body["latest_run"]["failed_regions"] == [
        {"region": "ap-northeast-1", "reason": "timeout", "attempts": 3}
    ]


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
    ]
    monkeypatch.setattr(active_snapshot.STATE, "issues", issues)
    resp = await client.get("/api/v1/admin/system-info", headers=admin_headers)
    kinds = [(i["kind"], i["service_code"]) for i in resp.json()["issues"]]
    assert kinds == [
        ("missing_regions", None),
        ("missing_icon", "ZZA"),
        ("missing_icon", "ZZB"),
    ]
    regions_issue = resp.json()["issues"][0]
    assert regions_issue["regions"] == ["eu-west-2"]
