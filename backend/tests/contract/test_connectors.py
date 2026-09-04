"""Contract test for POST /architectures/{id}/connectors (spec FR-008)."""

import uuid

import pytest


async def _create_arch_with_two_collections(client, auth_headers):
    arch = await client.post(
        "/api/v1/architectures", json={"name": "Arch", "provider": "aws"}, headers=auth_headers
    )
    arch_id = arch.json()["id"]
    c1 = await client.post(
        f"/api/v1/architectures/{arch_id}/collections",
        json={"type": "vpc", "name": "VPC A"},
        headers=auth_headers,
    )
    c2 = await client.post(
        f"/api/v1/architectures/{arch_id}/collections",
        json={"type": "vpc", "name": "VPC B"},
        headers=auth_headers,
    )
    return arch_id, c1.json()["id"], c2.json()["id"]


@pytest.mark.asyncio
async def test_create_connector(client, auth_headers):
    arch_id, c1, c2 = await _create_arch_with_two_collections(client, auth_headers)
    resp = await client.post(
        f"/api/v1/architectures/{arch_id}/connectors",
        json={"from_collection_id": c1, "to_collection_id": c2},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["from_collection_id"] == c1
    assert body["to_collection_id"] == c2
    assert body["sku_selection"] is None


@pytest.mark.asyncio
async def test_self_connect_rejected(client, auth_headers):
    arch_id, c1, _ = await _create_arch_with_two_collections(client, auth_headers)
    resp = await client.post(
        f"/api/v1/architectures/{arch_id}/connectors",
        json={"from_collection_id": c1, "to_collection_id": c1},
        headers=auth_headers,
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_connector_rejected_if_collection_not_in_architecture(client, auth_headers):
    arch_id, c1, _c2 = await _create_arch_with_two_collections(client, auth_headers)
    resp = await client.post(
        f"/api/v1/architectures/{arch_id}/connectors",
        json={"from_collection_id": c1, "to_collection_id": str(uuid.uuid4())},
        headers=auth_headers,
    )
    assert resp.status_code == 400
