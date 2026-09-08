"""Contract test for PATCH /collections/{id} (spec FR-001-FR-004)."""

import uuid

import pytest


async def _make_architecture_with(client, auth_headers, *collection_types: str) -> tuple[str, list[str]]:
    arch = await client.post(
        "/api/v1/architectures", json={"name": "Arch", "provider": "aws"}, headers=auth_headers
    )
    arch_id = arch.json()["id"]
    collection_ids = []
    for t in collection_types:
        resp = await client.post(
            f"/api/v1/architectures/{arch_id}/collections",
            json={"type": t, "name": t},
            headers=auth_headers,
        )
        collection_ids.append(resp.json()["id"])
    return arch_id, collection_ids


@pytest.mark.asyncio
async def test_nest_application_component_into_vpc(client, auth_headers):
    _arch_id, (vpc_id, app_id) = await _make_architecture_with(
        client, auth_headers, "vpc", "application_component"
    )

    resp = await client.patch(
        f"/api/v1/collections/{app_id}",
        json={"parent_collection_id": vpc_id},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["parent_collection_id"] == vpc_id


@pytest.mark.asyncio
async def test_move_between_vpcs(client, auth_headers):
    _arch_id, (vpc1_id, vpc2_id, app_id) = await _make_architecture_with(
        client, auth_headers, "vpc", "vpc", "application_component"
    )
    await client.patch(
        f"/api/v1/collections/{app_id}",
        json={"parent_collection_id": vpc1_id},
        headers=auth_headers,
    )

    resp = await client.patch(
        f"/api/v1/collections/{app_id}",
        json={"parent_collection_id": vpc2_id},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["parent_collection_id"] == vpc2_id


@pytest.mark.asyncio
async def test_unnest(client, auth_headers):
    _arch_id, (vpc_id, app_id) = await _make_architecture_with(
        client, auth_headers, "vpc", "application_component"
    )
    await client.patch(
        f"/api/v1/collections/{app_id}",
        json={"parent_collection_id": vpc_id},
        headers=auth_headers,
    )

    resp = await client.patch(
        f"/api/v1/collections/{app_id}",
        json={"parent_collection_id": None},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["parent_collection_id"] is None


@pytest.mark.asyncio
async def test_reject_nesting_a_vpc(client, auth_headers):
    """FR-004: a VPC can never be nested, even inside another VPC."""
    _arch_id, (vpc1_id, vpc2_id) = await _make_architecture_with(client, auth_headers, "vpc", "vpc")

    resp = await client.patch(
        f"/api/v1/collections/{vpc2_id}",
        json={"parent_collection_id": vpc1_id},
        headers=auth_headers,
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_reject_nonexistent_parent(client, auth_headers):
    _arch_id, (app_id,) = await _make_architecture_with(client, auth_headers, "application_component")

    resp = await client.patch(
        f"/api/v1/collections/{app_id}",
        json={"parent_collection_id": str(uuid.uuid4())},
        headers=auth_headers,
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_reject_parent_from_a_different_architecture(client, auth_headers):
    _arch1_id, (app_id,) = await _make_architecture_with(client, auth_headers, "application_component")
    _arch2_id, (other_vpc_id,) = await _make_architecture_with(client, auth_headers, "vpc")

    resp = await client.patch(
        f"/api/v1/collections/{app_id}",
        json={"parent_collection_id": other_vpc_id},
        headers=auth_headers,
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_nonexistent_collection_returns_404(client, auth_headers):
    resp = await client.patch(
        f"/api/v1/collections/{uuid.uuid4()}",
        json={"parent_collection_id": None},
        headers=auth_headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_setting_the_same_parent_again_is_idempotent(client, auth_headers):
    _arch_id, (vpc_id, app_id) = await _make_architecture_with(
        client, auth_headers, "vpc", "application_component"
    )
    body = {"parent_collection_id": vpc_id}
    first = await client.patch(f"/api/v1/collections/{app_id}", json=body, headers=auth_headers)
    second = await client.patch(f"/api/v1/collections/{app_id}", json=body, headers=auth_headers)

    assert first.status_code == second.status_code == 200
    assert first.json()["parent_collection_id"] == second.json()["parent_collection_id"] == vpc_id
