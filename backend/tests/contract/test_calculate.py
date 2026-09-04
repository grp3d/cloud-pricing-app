"""Contract test for POST /architectures/{id}/calculate (spec FR-010, FR-011, FR-012)."""

import pytest

KNOWN_SKU = "NN4EGUUQRWVYP98C"  # real t3.medium Linux on-demand SKU, ~$0.0416/hr
KNOWN_SERVICE_CODE = "AmazonEC2"


@pytest.mark.asyncio
async def test_calculate_sums_priceable_line_items(client, auth_headers):
    arch = await client.post(
        "/api/v1/architectures", json={"name": "Calc Arch", "provider": "aws"}, headers=auth_headers
    )
    arch_id = arch.json()["id"]
    coll = await client.post(
        f"/api/v1/architectures/{arch_id}/collections",
        json={"type": "application_component", "name": "Web"},
        headers=auth_headers,
    )
    coll_id = coll.json()["id"]
    await client.post(
        f"/api/v1/collections/{coll_id}/sku-selections",
        json={
            "service_code": KNOWN_SERVICE_CODE,
            "sku": KNOWN_SKU,
            "pricing_term": "on_demand",
            "purchase_option": "not_applicable",
            "usage_quantity": "730",
        },
        headers=auth_headers,
    )

    resp = await client.post(f"/api/v1/architectures/{arch_id}/calculate", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["snapshot_date"]
    assert float(body["total_price"]) > 0
    assert len(body["line_items"]) == 1
    assert body["line_items"][0]["priceable"] is True
    assert body["unpriceable"] == []


@pytest.mark.asyncio
async def test_calculate_flags_unpriceable_sku_without_estimating(client, auth_headers):
    arch = await client.post(
        "/api/v1/architectures", json={"name": "Calc Arch 2", "provider": "aws"}, headers=auth_headers
    )
    arch_id = arch.json()["id"]
    coll = await client.post(
        f"/api/v1/architectures/{arch_id}/collections",
        json={"type": "application_component", "name": "Web"},
        headers=auth_headers,
    )
    coll_id = coll.json()["id"]
    await client.post(
        f"/api/v1/collections/{coll_id}/sku-selections",
        json={
            "service_code": KNOWN_SERVICE_CODE,
            "sku": "DOES-NOT-EXIST-SKU",
            "pricing_term": "on_demand",
            "purchase_option": "not_applicable",
            "usage_quantity": "1",
        },
        headers=auth_headers,
    )

    resp = await client.post(f"/api/v1/architectures/{arch_id}/calculate", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_price"] == "0"
    assert len(body["unpriceable"]) == 1
    assert body["line_items"][0]["priceable"] is False
    assert body["line_items"][0]["price"] is None
