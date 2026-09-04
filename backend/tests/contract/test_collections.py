"""Contract test for POST /architectures/{id}/collections (spec FR-004)."""

import uuid

import pytest


async def _create_architecture(client, auth_headers) -> str:
    resp = await client.post(
        "/api/v1/architectures", json={"name": "Arch", "provider": "aws"}, headers=auth_headers
    )
    return resp.json()["id"]


@pytest.mark.asyncio
@pytest.mark.parametrize("collection_type", ["application_component", "vpc"])
async def test_create_collection_both_types(client, auth_headers, collection_type):
    arch_id = await _create_architecture(client, auth_headers)
    resp = await client.post(
        f"/api/v1/architectures/{arch_id}/collections",
        json={"type": collection_type, "name": "Web tier"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["type"] == collection_type
    assert body["sku_selections"] == []


@pytest.mark.asyncio
async def test_invalid_collection_type_rejected(client, auth_headers):
    arch_id = await _create_architecture(client, auth_headers)
    resp = await client.post(
        f"/api/v1/architectures/{arch_id}/collections",
        json={"type": "machine", "name": "Nope"},
        headers=auth_headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_cannot_add_collection_to_another_users_architecture(client, auth_headers):
    arch_id = await _create_architecture(client, auth_headers)
    other_headers = {"Authorization": f"Bearer {uuid.uuid4()}"}
    resp = await client.post(
        f"/api/v1/architectures/{arch_id}/collections",
        json={"type": "vpc", "name": "Nope"},
        headers=other_headers,
    )
    assert resp.status_code == 404
