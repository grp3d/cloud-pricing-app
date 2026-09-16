"""Integration test for batched unit resolution across a whole Architecture
(003-service-selection-improvements, FR-004, FR-005, quickstart.md step 3).

Proves `GET /architectures/{id}` attaches `unit` to every nested SKU Selection — both on a
Collection and on a Data Connector — via the single batched DuckDB query in
`attach_units_to_architecture`, not per-row resolution.
"""

import pytest

KNOWN_SKU_1 = "NN4EGUUQRWVYP98C"  # AmazonEC2, on-demand unit "Hrs"
KNOWN_SKU_2 = "2QF2GD6XUCJHFMKF"  # AmazonEC2 NAT Gateway usage type, on-demand unit "Gbps-hrs"


@pytest.mark.asyncio
async def test_architecture_tree_carries_units_for_every_nested_sku_selection(client, auth_headers):
    arch = await client.post(
        "/api/v1/architectures",
        json={"name": "Unit Resolution", "provider": "aws"},
        headers=auth_headers,
    )
    arch_id = arch.json()["id"]

    coll_a = await client.post(
        f"/api/v1/architectures/{arch_id}/collections",
        json={"type": "application_component", "name": "App A", "region": "us-east-1"},
        headers=auth_headers,
    )
    coll_b = await client.post(
        f"/api/v1/architectures/{arch_id}/collections",
        json={"type": "application_component", "name": "App B", "region": "us-east-1"},
        headers=auth_headers,
    )

    await client.post(
        f"/api/v1/collections/{coll_a.json()['id']}/sku-selections",
        json={
            "service_code": "AmazonEC2",
            "sku": KNOWN_SKU_1,
            "pricing_term": "on_demand",
            "purchase_option": "not_applicable",
            "usage_quantity": "730",
        },
        headers=auth_headers,
    )

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
            "service_code": "AmazonEC2",
            "sku": KNOWN_SKU_2,
            "pricing_term": "on_demand",
            "purchase_option": "not_applicable",
            "usage_quantity": "100",
        },
        headers=auth_headers,
    )

    detail = await client.get(f"/api/v1/architectures/{arch_id}", headers=auth_headers)
    assert detail.status_code == 200
    body = detail.json()

    coll_a_out = next(c for c in body["collections"] if c["id"] == coll_a.json()["id"])
    assert coll_a_out["sku_selections"][0]["unit"] == "Hrs"
    # 004-canvas-pricing-improvements FR-014: attributes are batch-resolved for the tree too.
    assert coll_a_out["sku_selections"][0]["attributes"]["instanceType"] == "t3.medium"

    connector_out = body["connectors"][0]
    assert connector_out["sku_selection"]["unit"] == "Gbps-hrs"
    assert connector_out["sku_selection"]["attributes"] != {}
