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


# --- 015-canvas-service-icons, contracts/api.md: SKUSelectionOut.product_family ---

NAT_GATEWAY_SKU = "2QF2GD6XUCJHFMKF"  # AmazonEC2, product family "NAT Gateway", us-east-1
S3_NO_FAMILY_SKU = "3Q77AV5KBQJMTNXB"  # AmazonS3, empty product family, us-east-1


def _selection(service_code: str, sku: str) -> dict:
    return {
        "service_code": service_code,
        "sku": sku,
        "pricing_term": "on_demand",
        "purchase_option": "not_applicable",
        "usage_quantity": "1",
    }


@pytest.mark.asyncio
async def test_get_architecture_includes_product_family(client, auth_headers):
    arch = await client.post(
        "/api/v1/architectures", json={"name": "Icons", "provider": "aws"}, headers=auth_headers
    )
    arch_id = arch.json()["id"]
    vpc_a = await client.post(
        f"/api/v1/architectures/{arch_id}/collections",
        json={"type": "vpc", "name": "VPC A", "region": "us-east-1"},
        headers=auth_headers,
    )
    vpc_b = await client.post(
        f"/api/v1/architectures/{arch_id}/collections",
        json={"type": "vpc", "name": "VPC B", "region": "us-east-1"},
        headers=auth_headers,
    )
    for payload in (
        _selection("AmazonEC2", NAT_GATEWAY_SKU),
        _selection("AmazonS3", S3_NO_FAMILY_SKU),
    ):
        created = await client.post(
            f"/api/v1/collections/{vpc_a.json()['id']}/sku-selections",
            json=payload,
            headers=auth_headers,
        )
        assert created.status_code == 201
    conn = await client.post(
        f"/api/v1/architectures/{arch_id}/connectors",
        json={"from_collection_id": vpc_a.json()["id"], "to_collection_id": vpc_b.json()["id"]},
        headers=auth_headers,
    )
    attached = await client.post(
        f"/api/v1/connectors/{conn.json()['id']}/sku-selection",
        json=_selection("AmazonEC2", NAT_GATEWAY_SKU),
        headers=auth_headers,
    )
    assert attached.status_code == 201

    resp = await client.get(f"/api/v1/architectures/{arch_id}", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    by_sku = {s["sku"]: s for c in body["collections"] for s in c["sku_selections"]}
    assert by_sku[NAT_GATEWAY_SKU]["product_family"] == "NAT Gateway"
    assert by_sku[S3_NO_FAMILY_SKU]["product_family"] is None
    assert body["connectors"][0]["sku_selection"]["product_family"] == "NAT Gateway"
