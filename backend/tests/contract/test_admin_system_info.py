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
    active_snapshot.get_active_snapshot()
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


# --- 019 (T039, contracts §9, FR-009): per-provider snapshot state ------------------------------


@pytest.mark.asyncio
async def test_every_provider_has_its_own_block(client, admin_headers):
    for code in ("aws", "azure", "gcp"):
        active_snapshot.get_active_snapshot(code)  # checked, as after startup
    body = (await client.get("/api/v1/admin/system-info", headers=admin_headers)).json()
    providers = body["providers"]
    assert set(providers) == {"aws", "azure", "gcp"}
    for block in providers.values():
        assert set(block) >= {"active_snapshot", "latest_run", "rejected", "issues", "status"}
        assert block["checked"] is True
        assert block["rejected"] is None and isinstance(block["issues"], list)
        assert block["latest_run"]["status"] == "succeeded"
    assert providers["aws"]["active_snapshot"] == body["active"]
    assert providers["azure"]["active_snapshot"]["snapshot_date"] == "2026-11-02"
    assert providers["azure"]["active_snapshot"]["regions"] == ["eastus"]
    assert providers["gcp"]["active_snapshot"]["regions"] == ["us-east1"]
    assert providers["azure"]["name"] == "Azure"


@pytest.mark.asyncio
async def test_a_failed_provider_shows_its_reason(client, admin_headers, tmp_path,
                                                  use_pricing_root):
    import json
    import shutil
    from pathlib import Path

    root = tmp_path / "root"
    shutil.copytree(Path(__file__).resolve().parents[1] / "fixtures" / "pricing_parquet", root)
    path = next((root / "gcp" / "manifests").glob("*/manifest.json"))
    manifest = json.loads(path.read_text())
    manifest["status"] = "failed"
    path.write_text(json.dumps(manifest))
    use_pricing_root(root)
    for code in ("azure", "gcp"):
        try:
            active_snapshot.get_active_snapshot(code)
        except Exception:  # noqa: BLE001 — GCP is meant to be unavailable
            pass
    providers = (await client.get("/api/v1/admin/system-info",
                                  headers=admin_headers)).json()["providers"]
    assert providers["gcp"]["status"] == "failed"
    assert providers["gcp"]["active_snapshot"] is None
    assert providers["gcp"]["reason"]
    assert providers["azure"]["status"] in {"current", "stale"}


# --- 019 (T070, contracts §9): price history per provider ---------------------------------------


@pytest.mark.asyncio
async def test_each_provider_has_a_history_block(client, admin_headers, tmp_path, monkeypatch):
    from src.config import settings
    from tests.helpers.history import build_trends_history

    monkeypatch.setattr(settings, "pricing_history_dir", str(tmp_path / "history"))
    build_trends_history(tmp_path / "history")
    providers = (await client.get("/api/v1/admin/system-info",
                                  headers=admin_headers)).json()["providers"]
    assert providers["aws"]["history"] == {
        "weeks_built": 4, "weeks_total": 4, "gaps": ["2026-09-28"], "backfill": "done",
        "last_error": None, "last_built_at": providers["aws"]["history"]["last_built_at"],
    }
    assert providers["aws"]["history"]["last_built_at"]
    assert providers["gcp"]["history"] == {
        "weeks_built": 0, "weeks_total": 0, "gaps": [], "backfill": "pending",
        "last_error": None, "last_built_at": None,
    }
