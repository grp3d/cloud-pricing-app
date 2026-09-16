"""Integration test for User Story 2 (quickstart.md section 2): connectors add to the total."""

import pytest

KNOWN_SKU = "2QF2GD6XUCJHFMKF"  # a real NAT Gateway usage-type SKU


@pytest.mark.asyncio
async def test_connector_attached_sku_cost_included_in_total(client, auth_headers):
    arch = await client.post(
        "/api/v1/architectures", json={"name": "US2 Arch", "provider": "aws"}, headers=auth_headers
    )
    arch_id = arch.json()["id"]
    c1 = await client.post(
        f"/api/v1/architectures/{arch_id}/collections",
        json={"type": "vpc", "name": "VPC A", "region": "us-east-1"},
        headers=auth_headers,
    )
    c2 = await client.post(
        f"/api/v1/architectures/{arch_id}/collections",
        json={"type": "vpc", "name": "VPC B", "region": "us-east-1"},
        headers=auth_headers,
    )

    # Two unconnected VPCs -> warn, but don't block (FR-017).
    calc_before = await client.post(
        f"/api/v1/architectures/{arch_id}/calculate", headers=auth_headers
    )
    assert calc_before.status_code == 200
    assert any(w["code"] == "unconnected_vpcs" for w in calc_before.json()["warnings"])

    conn = await client.post(
        f"/api/v1/architectures/{arch_id}/connectors",
        json={"from_collection_id": c1.json()["id"], "to_collection_id": c2.json()["id"]},
        headers=auth_headers,
    )
    conn_id = conn.json()["id"]

    await client.post(
        f"/api/v1/connectors/{conn_id}/sku-selection",
        json={
            "service_code": "AmazonEC2",
            "sku": KNOWN_SKU,
            "pricing_term": "on_demand",
            "purchase_option": "not_applicable",
            "usage_quantity": "100",
        },
        headers=auth_headers,
    )

    calc_after = await client.post(
        f"/api/v1/architectures/{arch_id}/calculate", headers=auth_headers
    )
    body = calc_after.json()
    assert body["warnings"] == []  # now connected
    assert len(body["line_items"]) == 1
    assert body["line_items"][0]["sku"] == KNOWN_SKU
    assert float(body["total_price"]) >= 0


@pytest.mark.asyncio
async def test_second_sku_on_an_occupied_connector_is_refused(client, auth_headers):
    """009-ui-fixes-next-iteration, US4, FR-008/contracts/api.md §1: a Connector that already
    has a SKUSelection MUST refuse a second one (409), not silently replace it — the existing
    selection MUST be unchanged afterward."""
    arch = await client.post(
        "/api/v1/architectures", json={"name": "US4 Arch", "provider": "aws"}, headers=auth_headers
    )
    arch_id = arch.json()["id"]
    c1 = await client.post(
        f"/api/v1/architectures/{arch_id}/collections",
        json={"type": "vpc", "name": "VPC A", "region": "us-east-1"},
        headers=auth_headers,
    )
    c2 = await client.post(
        f"/api/v1/architectures/{arch_id}/collections",
        json={"type": "vpc", "name": "VPC B", "region": "us-east-1"},
        headers=auth_headers,
    )
    conn = await client.post(
        f"/api/v1/architectures/{arch_id}/connectors",
        json={"from_collection_id": c1.json()["id"], "to_collection_id": c2.json()["id"]},
        headers=auth_headers,
    )
    conn_id = conn.json()["id"]

    first = await client.post(
        f"/api/v1/connectors/{conn_id}/sku-selection",
        json={
            "service_code": "AmazonEC2",
            "sku": KNOWN_SKU,
            "pricing_term": "on_demand",
            "purchase_option": "not_applicable",
            "usage_quantity": "100",
        },
        headers=auth_headers,
    )
    assert first.status_code == 201
    first_selection_id = first.json()["id"]

    second = await client.post(
        f"/api/v1/connectors/{conn_id}/sku-selection",
        json={
            "service_code": "AmazonEC2",
            "sku": "2QF2GD6XUCJHFMKF",
            "pricing_term": "on_demand",
            "purchase_option": "not_applicable",
            "usage_quantity": "50",
        },
        headers=auth_headers,
    )
    assert second.status_code == 409
    assert "detail" in second.json()

    arch_after = await client.get(f"/api/v1/architectures/{arch_id}", headers=auth_headers)
    connectors = arch_after.json()["connectors"]
    assert len(connectors) == 1
    assert connectors[0]["sku_selection"]["id"] == first_selection_id
    assert connectors[0]["sku_selection"]["usage_quantity"] == "100.0000"
