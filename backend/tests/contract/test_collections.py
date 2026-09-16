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
        json={"type": collection_type, "name": "Web tier", "region": "us-east-1"},
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
        json={"type": "vpc", "name": "Nope", "region": "us-east-1"},
        headers=other_headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_create_without_region_or_parent_rejected(client, auth_headers):
    arch_id = await _create_architecture(client, auth_headers)
    resp = await client.post(
        f"/api/v1/architectures/{arch_id}/collections",
        json={"type": "vpc", "name": "No region"},
        headers=auth_headers,
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_create_with_unavailable_region_rejected(client, auth_headers):
    arch_id = await _create_architecture(client, auth_headers)
    resp = await client.post(
        f"/api/v1/architectures/{arch_id}/collections",
        json={"type": "vpc", "name": "Bad region", "region": "mars-central-1"},
        headers=auth_headers,
    )
    assert resp.status_code == 400


# --- 010-multi-region-support, US1/FR-001a: create-with-parent inherits the VPC's region ---


@pytest.mark.asyncio
async def test_create_application_with_parent_inherits_vpc_region_and_ignores_client_region(
    client, auth_headers
):
    arch_id = await _create_architecture(client, auth_headers)
    vpc = await client.post(
        f"/api/v1/architectures/{arch_id}/collections",
        json={"type": "vpc", "name": "VPC", "region": "eu-west-1"},
        headers=auth_headers,
    )
    vpc_id = vpc.json()["id"]

    resp = await client.post(
        f"/api/v1/architectures/{arch_id}/collections",
        json={
            "type": "application_component",
            "name": "App",
            "region": "us-west-2",  # deliberately wrong — must be ignored
            "parent_collection_id": vpc_id,
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["region"] == "eu-west-1"
    assert body["parent_collection_id"] == vpc_id


@pytest.mark.asyncio
async def test_create_vpc_with_parent_collection_id_rejected(client, auth_headers):
    arch_id = await _create_architecture(client, auth_headers)
    vpc = await client.post(
        f"/api/v1/architectures/{arch_id}/collections",
        json={"type": "vpc", "name": "VPC", "region": "us-east-1"},
        headers=auth_headers,
    )
    resp = await client.post(
        f"/api/v1/architectures/{arch_id}/collections",
        json={
            "type": "vpc",
            "name": "Another VPC",
            "parent_collection_id": vpc.json()["id"],
        },
        headers=auth_headers,
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_create_with_parent_referencing_non_vpc_rejected(client, auth_headers):
    arch_id = await _create_architecture(client, auth_headers)
    other_app = await client.post(
        f"/api/v1/architectures/{arch_id}/collections",
        json={"type": "application_component", "name": "Not a VPC", "region": "us-east-1"},
        headers=auth_headers,
    )
    resp = await client.post(
        f"/api/v1/architectures/{arch_id}/collections",
        json={
            "type": "application_component",
            "name": "App",
            "parent_collection_id": other_app.json()["id"],
        },
        headers=auth_headers,
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_create_with_nonexistent_parent_rejected(client, auth_headers):
    arch_id = await _create_architecture(client, auth_headers)
    resp = await client.post(
        f"/api/v1/architectures/{arch_id}/collections",
        json={
            "type": "application_component",
            "name": "App",
            "parent_collection_id": str(uuid.uuid4()),
        },
        headers=auth_headers,
    )
    assert resp.status_code == 400


# --- 010-multi-region-support, US2/FR-003: PATCH /collections/{id} region lock ---


@pytest.mark.asyncio
async def test_update_region_succeeds_while_collection_is_empty(client, auth_headers):
    arch_id = await _create_architecture(client, auth_headers)
    vpc = await client.post(
        f"/api/v1/architectures/{arch_id}/collections",
        json={"type": "vpc", "name": "VPC", "region": "us-east-1"},
        headers=auth_headers,
    )
    vpc_id = vpc.json()["id"]

    resp = await client.patch(
        f"/api/v1/collections/{vpc_id}", json={"region": "eu-west-2"}, headers=auth_headers
    )
    assert resp.status_code == 200
    assert resp.json()["region"] == "eu-west-2"


@pytest.mark.asyncio
async def test_update_region_rejected_with_409_once_collection_has_a_service(client, auth_headers):
    arch_id = await _create_architecture(client, auth_headers)
    app = await client.post(
        f"/api/v1/architectures/{arch_id}/collections",
        json={"type": "application_component", "name": "App", "region": "us-east-1"},
        headers=auth_headers,
    )
    app_id = app.json()["id"]
    await client.post(
        f"/api/v1/collections/{app_id}/sku-selections",
        json={
            "service_code": "AmazonEC2",
            "sku": "NN4EGUUQRWVYP98C",
            "pricing_term": "on_demand",
            "purchase_option": "not_applicable",
            "usage_quantity": "1",
        },
        headers=auth_headers,
    )

    resp = await client.patch(
        f"/api/v1/collections/{app_id}", json={"region": "eu-west-2"}, headers=auth_headers
    )
    assert resp.status_code == 409

    unchanged = await client.get(f"/api/v1/architectures/{arch_id}", headers=auth_headers)
    app_after = next(c for c in unchanged.json()["collections"] if c["id"] == app_id)
    assert app_after["region"] == "us-east-1"


@pytest.mark.asyncio
async def test_update_region_rejected_with_409_once_vpc_has_a_nested_application(
    client, auth_headers
):
    arch_id = await _create_architecture(client, auth_headers)
    vpc = await client.post(
        f"/api/v1/architectures/{arch_id}/collections",
        json={"type": "vpc", "name": "VPC", "region": "us-east-1"},
        headers=auth_headers,
    )
    vpc_id = vpc.json()["id"]
    await client.post(
        f"/api/v1/architectures/{arch_id}/collections",
        json={
            "type": "application_component",
            "name": "App",
            "parent_collection_id": vpc_id,
        },
        headers=auth_headers,
    )

    resp = await client.patch(
        f"/api/v1/collections/{vpc_id}", json={"region": "eu-west-2"}, headers=auth_headers
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_update_region_to_unavailable_region_rejected(client, auth_headers):
    arch_id = await _create_architecture(client, auth_headers)
    vpc = await client.post(
        f"/api/v1/architectures/{arch_id}/collections",
        json={"type": "vpc", "name": "VPC", "region": "us-east-1"},
        headers=auth_headers,
    )
    resp = await client.patch(
        f"/api/v1/collections/{vpc.json()['id']}",
        json={"region": "mars-central-1"},
        headers=auth_headers,
    )
    assert resp.status_code == 400
