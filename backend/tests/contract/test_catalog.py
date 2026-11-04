"""Contract test for GET /catalog/skus (spec FR-005, FR-018).

Runs against the real AWS pricing Parquet data (read-only, DuckDB-backed) — there is no mock
to substitute here per Constitution Principle I (only ever query the real source).
"""

import pytest

from src import config as config_module


@pytest.mark.asyncio
async def test_search_by_service_and_family(client, auth_headers):
    resp = await client.get(
        "/api/v1/catalog/skus",
        params={
            "service_code": "AmazonEC2",
            "product_family": "Compute Instance",
            "limit": 5,
            "region": "us-east-1",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["snapshot_date"]
    # 018-app-cloud-deployment, FR-059.
    assert isinstance(body["snapshot_revision"], int) and body["snapshot_revision"] >= 1
    assert len(body["results"]) > 0
    assert all(r["service_code"] == "AmazonEC2" for r in body["results"])
    assert all(r["product_family"] == "Compute Instance" for r in body["results"])


@pytest.mark.asyncio
async def test_search_results_include_attributes_and_unit(client, auth_headers):
    """003-service-selection-improvements FR-001, FR-002, FR-004, FR-005."""
    resp = await client.get(
        "/api/v1/catalog/skus",
        params={
            "service_code": "AmazonEC2",
            "product_family": "Compute Instance",
            "q": "t3.medium",
            "limit": 1,
            "region": "us-east-1",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200
    result = resp.json()["results"][0]
    assert isinstance(result["attributes"], dict)
    assert result["attributes"]["instanceType"] == "t3.medium"
    assert result["unit"] == "Hrs"


@pytest.mark.asyncio
async def test_search_results_attributes_is_never_null(client, auth_headers):
    """A SKU with no descriptive attributes shows {} — never null (FR-003)."""
    resp = await client.get(
        "/api/v1/catalog/skus",
        params={
            "service_code": "AmazonEC2",
            "product_family": "Compute Instance",
            "limit": 5,
            "region": "us-east-1",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200
    for result in resp.json()["results"]:
        assert result["attributes"] is not None
        assert isinstance(result["attributes"], dict)


@pytest.mark.asyncio
async def test_search_with_no_filters_returns_400(client, auth_headers):
    resp = await client.get(
        "/api/v1/catalog/skus", params={"region": "us-east-1"}, headers=auth_headers
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_search_with_no_matches_returns_empty_not_error(client, auth_headers):
    resp = await client.get(
        "/api/v1/catalog/skus",
        params={"service_code": "ThisServiceDoesNotExist", "region": "us-east-1"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["results"] == []


@pytest.mark.asyncio
async def test_data_source_outage_returns_503(client, auth_headers, use_pricing_root, tmp_path):
    """A real outage (the active snapshot's files are gone) is a distinct 503, never a
    200/empty result."""
    import shutil
    from pathlib import Path

    copy = tmp_path / "pipeline"
    shutil.copytree(Path(config_module.settings.pricing_data_source.root), copy)
    use_pricing_root(copy)
    shutil.rmtree(copy / "aws" / "parquet")
    resp = await client.get(
        "/api/v1/catalog/skus",
        params={"service_code": "AmazonEC2", "region": "us-east-1"},
        headers=auth_headers,
    )
    assert resp.status_code == 503
    assert resp.json()["error"] == "pricing_data_unavailable"


# --- 019-gcp-azure-providers-trends (T034, contracts §2, §3) ----------------------------------


async def _search(client, auth_headers, **params):
    return await client.get("/api/v1/catalog/skus", params=params, headers=auth_headers)


@pytest.mark.asyncio
async def test_azure_search_with_q_kind_and_product_family(client, auth_headers):
    resp = await _search(client, auth_headers, provider="azure", region="eastus", kind="vm")
    assert resp.status_code == 200
    body = resp.json()
    assert body["snapshot_date"] == "2026-11-02"
    (vm,) = body["results"]
    assert vm["provider"] == "azure"
    assert vm["sku"] == "DZH318Z08M9W/004T/db8c0962-f3f8-5b44-99aa-f3c7c1e668c8"
    assert vm["service_code"] == "DZH313Z7MMC8"
    assert vm["kind"] == "vm"
    assert vm["location_scope"] == "regional"
    assert vm["unit"] == "1 Hour"
    assert vm["price_types"] == ["on_demand", "reserved_1yr", "reserved_3yr",
                                 "savings_plan_1yr", "savings_plan_3yr"]

    resp = await _search(client, auth_headers, provider="azure", region="eastus",
                         product_family="Managed Disks", q="P10")
    assert [r["product_family"] for r in resp.json()["results"]] == ["Premium SSD Managed Disks"]


@pytest.mark.asyncio
async def test_gcp_search_marks_global_and_multi_regional_items(client, auth_headers):
    resp = await _search(client, auth_headers, provider="gcp", region="us-east1",
                         q="Licensing|^N2 Instance Core")
    by_sku = {r["sku"]: r for r in resp.json()["results"]}
    assert by_sku["92D2-8A8F-DF54"]["location_scope"] == "global"
    assert by_sku["BB77-5FDA-69D9"]["location_scope"] == "multi_regional"
    assert by_sku["BB77-5FDA-69D9"]["price_types"] == ["on_demand", "commitment_1yr",
                                                       "commitment_3yr"]


@pytest.mark.asyncio
async def test_aws_results_have_the_new_fields_with_defaults(client, auth_headers):
    resp = await _search(client, auth_headers, region="us-east-1", service_code="AmazonEC2",
                         limit=1)
    (row,) = resp.json()["results"]
    assert (row["provider"], row["location_scope"], row["kind"], row["price_types"]) == (
        "aws", "regional", None, []
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("param", ["from_region_code", "to_region_code"])
async def test_aws_only_parameters_are_refused_for_other_providers(client, auth_headers, param):
    resp = await _search(client, auth_headers, provider="gcp", region="us-east1", q="N2",
                         **{param: "us-east-1"})
    assert resp.status_code == 422
    assert resp.json()["detail"][0]["loc"] == ["query", param]


@pytest.mark.asyncio
async def test_kind_is_refused_for_aws_and_unknown_kinds_are_422(client, auth_headers):
    assert (await _search(client, auth_headers, region="us-east-1", kind="vm")).status_code == 422
    resp = await _search(client, auth_headers, provider="azure", region="eastus", kind="spaceship")
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_other_provider_regions_are_validated(client, auth_headers):
    resp = await _search(client, auth_headers, provider="azure", region="us-east-1", q="D4s")
    assert resp.status_code == 422
    resp = await _search(client, auth_headers, provider="azure", region="eastus")
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_regions_per_provider(client, auth_headers):
    gcp = await client.get("/api/v1/regions", params={"provider": "gcp"}, headers=auth_headers)
    assert gcp.json() == {"regions": [{"code": "us-east1", "display_name": "us-east1"}]}
    azure = await client.get("/api/v1/regions", params={"provider": "azure"}, headers=auth_headers)
    assert azure.json() == {"regions": [{"code": "eastus", "display_name": "US East"}]}
    aws = (await client.get("/api/v1/regions", headers=auth_headers)).json()["regions"]
    assert all(r["display_name"] == r["code"] for r in aws)
    bad = await client.get("/api/v1/regions", params={"provider": "oracle"}, headers=auth_headers)
    assert bad.status_code == 422
