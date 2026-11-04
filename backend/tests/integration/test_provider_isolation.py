"""One provider's broken snapshot never affects the others (019, T037, SC-008): with GCP's
newest manifest `failed`, AWS and Azure create, search and calculate normally, and GCP answers
503 with its reason."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from tests.helpers.providers import build_architecture

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "pricing_parquet"


@pytest.fixture
def gcp_failed(tmp_path, use_pricing_root):
    root = tmp_path / "root"
    shutil.copytree(FIXTURE_ROOT, root)
    path = next((root / "gcp" / "manifests").glob("*/manifest.json"))
    manifest = json.loads(path.read_text())
    manifest["status"] = "failed"
    path.write_text(json.dumps(manifest))
    use_pricing_root(root)


@pytest.mark.asyncio
async def test_aws_and_azure_work_while_gcp_is_failed(client, auth_headers, gcp_failed):
    providers = {p["code"]: p for p in
                 (await client.get("/api/v1/providers", headers=auth_headers)).json()}
    assert providers["gcp"]["active"] is False and providers["gcp"]["status"] == "failed"
    assert providers["aws"]["active"] and providers["azure"]["active"]

    arch_id = await build_architecture(client, auth_headers, "azure")
    calc = await client.post(f"/api/v1/architectures/{arch_id}/calculate", headers=auth_headers)
    assert calc.status_code == 200 and calc.json()["unpriceable"] == []
    search = await client.get("/api/v1/catalog/skus", headers=auth_headers,
                              params={"provider": "azure", "region": "eastus", "kind": "vm"})
    assert search.status_code == 200 and search.json()["total"] == 1
    aws = await client.get("/api/v1/catalog/skus", headers=auth_headers,
                           params={"region": "us-east-1", "service_code": "AmazonEC2",
                                   "limit": 1})
    assert aws.status_code == 200

    for resp in (
        await client.get("/api/v1/regions", params={"provider": "gcp"}, headers=auth_headers),
        await client.get("/api/v1/catalog/skus", headers=auth_headers,
                         params={"provider": "gcp", "region": "us-east1", "q": "N2"}),
    ):
        assert resp.status_code == 503
        body = resp.json()
        assert (body["error"], body["provider"]) == ("pricing_data_unavailable", "gcp")
        assert body["reason"] and "GCP" in body["message"]
