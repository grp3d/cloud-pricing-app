"""Contract tests for Architecture endpoints (spec FR-001, FR-002, FR-013, FR-014)."""

import uuid

import pytest


@pytest.mark.asyncio
async def test_create_architecture(client, auth_headers):
    resp = await client.post(
        "/api/v1/architectures", json={"name": "My Arch", "provider": "aws"}, headers=auth_headers
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "My Arch"
    assert body["provider"] == "aws"
    assert "id" in body


@pytest.mark.asyncio
async def test_non_aws_provider_rejected(client, auth_headers):
    resp = await client.post(
        "/api/v1/architectures", json={"name": "x", "provider": "gcp"}, headers=auth_headers
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_list_only_returns_own_architectures(client, auth_headers):
    other_user_headers = {"Authorization": f"Bearer {uuid.uuid4()}"}
    await client.post(
        "/api/v1/architectures", json={"name": "Mine", "provider": "aws"}, headers=auth_headers
    )
    await client.post(
        "/api/v1/architectures",
        json={"name": "Theirs", "provider": "aws"},
        headers=other_user_headers,
    )

    resp = await client.get("/api/v1/architectures?provider=aws", headers=auth_headers)
    names = [a["name"] for a in resp.json()]
    assert names == ["Mine"]


@pytest.mark.asyncio
async def test_get_architecture_includes_collections_and_connectors(client, auth_headers):
    create = await client.post(
        "/api/v1/architectures", json={"name": "Detail", "provider": "aws"}, headers=auth_headers
    )
    arch_id = create.json()["id"]

    resp = await client.get(f"/api/v1/architectures/{arch_id}", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["collections"] == []
    assert body["connectors"] == []


@pytest.mark.asyncio
async def test_get_nonexistent_architecture_404(client, auth_headers):
    resp = await client.get(f"/api/v1/architectures/{uuid.uuid4()}", headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_cannot_get_another_users_architecture(client, auth_headers):
    other_user_headers = {"Authorization": f"Bearer {uuid.uuid4()}"}
    create = await client.post(
        "/api/v1/architectures", json={"name": "Private", "provider": "aws"}, headers=auth_headers
    )
    arch_id = create.json()["id"]

    resp = await client.get(f"/api/v1/architectures/{arch_id}", headers=other_user_headers)
    assert resp.status_code == 404
