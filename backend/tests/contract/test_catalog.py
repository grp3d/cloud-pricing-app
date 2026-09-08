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
        params={"service_code": "AmazonEC2", "product_family": "Compute Instance", "limit": 5},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["snapshot_date"]
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
        params={"service_code": "AmazonEC2", "product_family": "Compute Instance", "limit": 5},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    for result in resp.json()["results"]:
        assert result["attributes"] is not None
        assert isinstance(result["attributes"], dict)


@pytest.mark.asyncio
async def test_search_with_no_filters_returns_400(client, auth_headers):
    resp = await client.get("/api/v1/catalog/skus", headers=auth_headers)
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_search_with_no_matches_returns_empty_not_error(client, auth_headers):
    resp = await client.get(
        "/api/v1/catalog/skus",
        params={"service_code": "ThisServiceDoesNotExist"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["results"] == []


@pytest.mark.asyncio
async def test_data_source_outage_returns_503(client, auth_headers, monkeypatch, tmp_path):
    """A real outage (unreadable Parquet dir) is a distinct 503, never a 200/empty result."""
    monkeypatch.setattr(
        config_module.settings, "aws_pricing_parquet_dir", str(tmp_path / "missing")
    )
    resp = await client.get(
        "/api/v1/catalog/skus", params={"service_code": "AmazonEC2"}, headers=auth_headers
    )
    assert resp.status_code == 503
    assert resp.json()["error"] == "pricing_data_unavailable"
