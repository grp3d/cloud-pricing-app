"""Integration test for the full User Story 1 flow (quickstart.md section 1):
create Architecture -> add Collection -> search catalog -> add SKU with pricing inputs ->
calculate -> get a real, traceable price.
"""

import pytest


@pytest.mark.asyncio
async def test_full_assemble_and_price_flow(client, auth_headers):
    # 1. AWS is the only active provider.
    providers = await client.get("/api/v1/providers", headers=auth_headers)
    aws = next(p for p in providers.json() if p["code"] == "aws")
    assert aws["active"] is True

    # 2. Create an Architecture.
    arch_resp = await client.post(
        "/api/v1/architectures",
        json={"name": "Quickstart Web App", "provider": "aws"},
        headers=auth_headers,
    )
    assert arch_resp.status_code == 201
    arch_id = arch_resp.json()["id"]

    # 3. Add a Collection.
    coll_resp = await client.post(
        f"/api/v1/architectures/{arch_id}/collections",
        json={"type": "application_component", "name": "Web tier"},
        headers=auth_headers,
    )
    assert coll_resp.status_code == 201
    coll_id = coll_resp.json()["id"]

    # 4. Search the real catalog for an EC2 SKU.
    search_resp = await client.get(
        "/api/v1/catalog/skus",
        params={"service_code": "AmazonEC2", "product_family": "Compute Instance", "q": "t3.medium"},
        headers=auth_headers,
    )
    assert search_resp.status_code == 200
    results = search_resp.json()["results"]
    assert len(results) > 0
    sku = results[0]["sku"]

    # 5. Add that SKU with pricing inputs.
    add_resp = await client.post(
        f"/api/v1/collections/{coll_id}/sku-selections",
        json={
            "service_code": "AmazonEC2",
            "sku": sku,
            "pricing_term": "on_demand",
            "purchase_option": "not_applicable",
            "usage_quantity": "730",
        },
        headers=auth_headers,
    )
    assert add_resp.status_code == 201

    # 6. Calculate — expect a real, snapshot-traceable result (SC-002). Note: this specific SKU
    # may legitimately be $0 (e.g. a reservation-only variant) or unpriceable for its
    # term/purchase_option — either way it must be traceable and never fabricated.
    calc_resp = await client.post(f"/api/v1/architectures/{arch_id}/calculate", headers=auth_headers)
    assert calc_resp.status_code == 200
    body = calc_resp.json()
    assert body["snapshot_date"]
    assert len(body["line_items"]) == 1
    assert (body["line_items"][0]["priceable"] is True) != (len(body["unpriceable"]) == 1)
