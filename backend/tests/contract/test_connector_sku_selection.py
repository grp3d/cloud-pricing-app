"""Contract test for POST /connectors/{id}/sku-selection (spec FR-009) and direct
DELETE /connectors/{id} (spec FR-015 — the direct-delete path, distinct from the
cascade-via-collection-delete path already covered in test_collection_delete_cascade.py).
"""

import pytest

KNOWN_SKU = "2QF2GD6XUCJHFMKF"  # a real NAT Gateway usage-type SKU
KNOWN_SERVICE_CODE = "AmazonEC2"


async def _create_connector(client, auth_headers) -> tuple[str, str]:
    arch = await client.post(
        "/api/v1/architectures", json={"name": "Arch", "provider": "aws"}, headers=auth_headers
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
    return arch_id, conn.json()["id"]


@pytest.mark.asyncio
async def test_attach_sku_to_connector(client, auth_headers):
    _arch_id, conn_id = await _create_connector(client, auth_headers)
    resp = await client.post(
        f"/api/v1/connectors/{conn_id}/sku-selection",
        json={
            "service_code": KNOWN_SERVICE_CODE,
            "sku": KNOWN_SKU,
            "pricing_term": "on_demand",
            "purchase_option": "not_applicable",
            "usage_quantity": "100",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    assert resp.json()["sku"] == KNOWN_SKU
    assert resp.json()["unit"] == "Gbps-hrs"


@pytest.mark.asyncio
async def test_reattaching_sku_is_refused_not_replaced(client, auth_headers):
    """009-ui-fixes-next-iteration, US4, FR-008: superseded 008's "replace" behavior — a second
    attach on an already-occupied Connector is now refused (409), and the original selection is
    left unchanged, rather than silently replaced. See contracts/api.md §1."""
    _arch_id, conn_id = await _create_connector(client, auth_headers)
    payload = {
        "service_code": KNOWN_SERVICE_CODE,
        "sku": KNOWN_SKU,
        "pricing_term": "on_demand",
        "purchase_option": "not_applicable",
        "usage_quantity": "100",
    }
    first = await client.post(
        f"/api/v1/connectors/{conn_id}/sku-selection", json=payload, headers=auth_headers
    )
    second = await client.post(
        f"/api/v1/connectors/{conn_id}/sku-selection",
        json={**payload, "usage_quantity": "200"},
        headers=auth_headers,
    )
    assert second.status_code == 409
    assert "detail" in second.json()

    # The original selection is untouched.
    detail = await client.get(f"/api/v1/architectures/{_arch_id}", headers=auth_headers)
    connectors = detail.json()["connectors"]
    assert len(connectors) == 1
    assert connectors[0]["sku_selection"]["id"] == first.json()["id"]
    assert connectors[0]["sku_selection"]["usage_quantity"] == "100.0000"


@pytest.mark.asyncio
async def test_direct_delete_connector(client, auth_headers):
    """The user deleting a connector directly (not via a Collection cascade) — spec FR-015."""
    arch_id, conn_id = await _create_connector(client, auth_headers)

    resp = await client.delete(f"/api/v1/connectors/{conn_id}", headers=auth_headers)
    assert resp.status_code == 204

    detail = await client.get(f"/api/v1/architectures/{arch_id}", headers=auth_headers)
    assert detail.json()["connectors"] == []
