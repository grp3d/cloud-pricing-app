"""Integration test: unpriceable/excluded services name their containing component(s)
(004-canvas-pricing-improvements, FR-012, FR-013, quickstart.md step 3).

One service attached directly to a Collection, one attached to a Data Connector — both must
name the right component(s) in the calculate response's `unpriceable` list.
"""

import pytest

NONEXISTENT_SKU = "DOES-NOT-EXIST-SKU"
KNOWN_SERVICE_CODE = "AmazonEC2"


@pytest.mark.asyncio
async def test_collection_and_connector_unpriceable_services_both_named(client, auth_headers):
    arch = await client.post(
        "/api/v1/architectures",
        json={"name": "Warning Components", "provider": "aws"},
        headers=auth_headers,
    )
    arch_id = arch.json()["id"]

    coll_a = await client.post(
        f"/api/v1/architectures/{arch_id}/collections",
        json={"type": "application_component", "name": "App A"},
        headers=auth_headers,
    )
    coll_b = await client.post(
        f"/api/v1/architectures/{arch_id}/collections",
        json={"type": "application_component", "name": "App B"},
        headers=auth_headers,
    )

    # A service directly on a Collection with no real price.
    await client.post(
        f"/api/v1/collections/{coll_a.json()['id']}/sku-selections",
        json={
            "service_code": KNOWN_SERVICE_CODE,
            "sku": NONEXISTENT_SKU,
            "pricing_term": "on_demand",
            "purchase_option": "not_applicable",
            "usage_quantity": "1",
        },
        headers=auth_headers,
    )

    # A service attached to a Data Connector, also with no real price.
    connector = await client.post(
        f"/api/v1/architectures/{arch_id}/connectors",
        json={
            "from_collection_id": coll_a.json()["id"],
            "to_collection_id": coll_b.json()["id"],
        },
        headers=auth_headers,
    )
    await client.post(
        f"/api/v1/connectors/{connector.json()['id']}/sku-selection",
        json={
            "service_code": KNOWN_SERVICE_CODE,
            "sku": NONEXISTENT_SKU,
            "pricing_term": "on_demand",
            "purchase_option": "not_applicable",
            "usage_quantity": "1",
        },
        headers=auth_headers,
    )

    resp = await client.post(f"/api/v1/architectures/{arch_id}/calculate", headers=auth_headers)
    assert resp.status_code == 200
    unpriceable = resp.json()["unpriceable"]
    assert len(unpriceable) == 2

    by_components = {tuple(u["components"]): u for u in unpriceable}
    assert ("App A",) in by_components
    assert ("Data Connector between App A and App B",) in by_components
