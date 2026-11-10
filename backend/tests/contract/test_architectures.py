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
async def test_unknown_provider_rejected(client, auth_headers):
    """019 (US1): was `test_non_aws_provider_rejected`; GCP and Azure are now supported."""
    resp = await client.post(
        "/api/v1/architectures", json={"name": "x", "provider": "oracle"}, headers=auth_headers
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["gcp", "azure"])
async def test_gcp_and_azure_architectures_can_be_created(client, auth_headers, provider):
    resp = await client.post(
        "/api/v1/architectures", json={"name": "x", "provider": provider}, headers=auth_headers
    )
    assert resp.status_code == 201
    assert resp.json()["provider"] == provider


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


# --- 020 (T017, contracts/api.md §2): SKUSelectionOut.service_name ----------------------------

from tests.helpers.providers import build_architecture  # noqa: E402


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider", "expected"),
    [
        ("gcp", {"BB77-5FDA-69D9": "Compute Engine", "6AE1-525F-8B80": "Compute Engine",
                 "F274-1692-F213": "Compute Engine"}),
        ("azure", {"DZH318Z08M9W/004T/db8c0962-f3f8-5b44-99aa-f3c7c1e668c8": "Virtual Machines",
                   "DZH318Z0BP04/0035/93a6a529-4f49-47cb-9b1e-db9e5f23263f": "Storage",
                   "DZH318Z0BNVX/001D/9995d93a-7d35-4d3f-9c69-7a7fea447ef4": "Bandwidth"}),
    ],
)
async def test_selections_carry_the_provider_service_name(client, auth_headers, provider,
                                                          expected):
    arch_id = await build_architecture(client, auth_headers, provider)
    body = (await client.get(f"/api/v1/architectures/{arch_id}", headers=auth_headers)).json()
    names = {s["sku"]: s["service_name"] for c in body["collections"] for s in c["sku_selections"]}
    assert names == expected


@pytest.mark.asyncio
async def test_aws_selections_have_no_service_name(client, auth_headers):
    """AWS icons never need it (FR-012: AWS unchanged), so it stays null."""
    arch = await client.post("/api/v1/architectures", json={"name": "N", "provider": "aws"},
                             headers=auth_headers)
    coll = await client.post(
        f"/api/v1/architectures/{arch.json()['id']}/collections",
        json={"type": "application_component", "name": "App", "region": "us-east-1"},
        headers=auth_headers,
    )
    created = await client.post(f"/api/v1/collections/{coll.json()['id']}/sku-selections",
                                json=_selection("AmazonEC2", NAT_GATEWAY_SKU),
                                headers=auth_headers)
    assert created.status_code == 201
    assert created.json()["service_name"] is None


# --- 021 (US7, FR-044): SKUSelectionOut.summary -----------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["gcp", "azure"])
async def test_gcp_and_azure_selections_carry_their_description(client, auth_headers, provider):
    arch_id = await build_architecture(client, auth_headers, provider)
    body = (await client.get(f"/api/v1/architectures/{arch_id}", headers=auth_headers)).json()
    selections = [s for c in body["collections"] for s in c["sku_selections"]]
    assert selections
    for s in selections:
        assert isinstance(s["summary"], str) and s["summary"].strip(), s["sku"]
        # The description is the item's own, not its service's name.
        assert s["summary"] != s["service_code"]


@pytest.mark.asyncio
async def test_aws_selections_have_no_summary(client, auth_headers):
    """AWS's readable details stay in `attributes` (unchanged), so `summary` stays null."""
    arch = await client.post(
        "/api/v1/architectures", json={"name": "N", "provider": "aws"}, headers=auth_headers
    )
    coll = await client.post(
        f"/api/v1/architectures/{arch.json()['id']}/collections",
        json={"type": "application_component", "name": "App", "region": "us-east-1"},
        headers=auth_headers,
    )
    await client.post(
        f"/api/v1/collections/{coll.json()['id']}/sku-selections",
        json=_selection("AmazonEC2", NAT_GATEWAY_SKU),
        headers=auth_headers,
    )
    body = (
        await client.get(f"/api/v1/architectures/{arch.json()['id']}", headers=auth_headers)
    ).json()
    assert body["collections"][0]["sku_selections"][0]["summary"] is None

