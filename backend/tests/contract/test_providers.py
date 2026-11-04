"""Contract test for GET /providers (spec FR-003)."""

import pytest


@pytest.mark.asyncio
async def test_every_provider_with_a_snapshot_is_active(client, auth_headers):
    """019 (US1): GCP and Azure have adapters and fixture snapshots, so all three are active
    (was `test_aws_active_gcp_azure_disabled` before US1)."""
    resp = await client.get("/api/v1/providers", headers=auth_headers)
    assert resp.status_code == 200
    by_code = {p["code"]: p for p in resp.json()}
    assert by_code["aws"]["active"] is True
    assert by_code["gcp"]["active"] is True
    assert by_code["azure"]["active"] is True


# --- 019-gcp-azure-providers-trends (contracts §1, FR-001, FR-002) ---------------------------

import shutil  # noqa: E402
from pathlib import Path  # noqa: E402

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "pricing_parquet"
USABLE = {"current", "partial", "stale"}


@pytest.mark.asyncio
async def test_each_provider_reports_status_and_snapshot(client, auth_headers):
    resp = await client.get("/api/v1/providers", headers=auth_headers)
    by_code = {p["code"]: p for p in resp.json()}
    assert set(by_code) == {"aws", "gcp", "azure"}
    for provider in by_code.values():
        assert set(provider) >= {"code", "name", "active", "status", "reason",
                                 "snapshot_date", "snapshot_revision"}
        assert provider["status"] in USABLE | {"failed", "none"}
        if provider["active"]:
            assert provider["status"] in USABLE
    aws = by_code["aws"]
    assert (aws["snapshot_date"], aws["snapshot_revision"]) == ("2026-09-24", 1)
    assert by_code["azure"]["snapshot_date"] == "2026-11-02"
    assert by_code["aws"]["status"] in USABLE


@pytest.mark.asyncio
async def test_a_provider_with_no_data_is_none_and_inactive(
    client, auth_headers, use_pricing_root, tmp_path
):
    root = tmp_path / "root"
    shutil.copytree(FIXTURE_ROOT, root)
    shutil.rmtree(root / "azure")
    use_pricing_root(root)
    by_code = {p["code"]: p for p in
               (await client.get("/api/v1/providers", headers=auth_headers)).json()}
    assert by_code["azure"] == {
        "code": "azure", "name": "Azure", "active": False, "status": "none",
        "reason": "no snapshot available", "snapshot_date": None, "snapshot_revision": None,
    }
    assert by_code["aws"]["active"] is True
