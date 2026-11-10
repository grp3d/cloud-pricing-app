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
        json={"type": "vpc", "name": "VPC A", "region": "us-east-1"},
        headers=auth_headers,
    )
    c2 = await client.post(
        f"/api/v1/architectures/{arch_id}/collections",
        json={"type": "vpc", "name": "VPC B", "region": "us-east-1"},
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


# --- 019 arrows (T096, FR-026, FR-028 to FR-030) --------------------------------------------


async def _connector(client, auth_headers, **fields):
    arch_id, c1, c2 = await _create_arch_with_two_collections(client, auth_headers)
    resp = await client.post(
        f"/api/v1/architectures/{arch_id}/connectors",
        json={"from_collection_id": c1, "to_collection_id": c2, **fields},
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    return arch_id, resp.json()


@pytest.mark.asyncio
async def test_a_new_connector_has_no_arrow(client, auth_headers):
    _arch, body = await _connector(client, auth_headers)
    assert (body["arrow_style"], body["arrow_reversed"]) == ("none", False)


@pytest.mark.asyncio
async def test_create_with_an_arrow_style(client, auth_headers):
    _arch, body = await _connector(client, auth_headers, arrow_style="one_way",
                                   arrow_reversed=True)
    assert (body["arrow_style"], body["arrow_reversed"]) == ("one_way", True)


@pytest.mark.asyncio
async def test_patch_arrow_style_and_reverse_without_a_data_transfer_selection(
    client, auth_headers
):
    _arch, body = await _connector(client, auth_headers)
    assert body["sku_selection"] is None
    url = f"/api/v1/connectors/{body['id']}"
    resp = await client.patch(url, json={"arrow_style": "two_way"}, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert (resp.json()["arrow_style"], resp.json()["arrow_reversed"]) == ("two_way", False)
    resp = await client.patch(url, json={"arrow_style": "one_way", "arrow_reversed": True},
                              headers=auth_headers)
    out = resp.json()
    # Reversing is visual only: from and to stay as they were.
    assert (out["arrow_style"], out["arrow_reversed"]) == ("one_way", True)
    assert (out["from_collection_id"], out["to_collection_id"]) == (
        body["from_collection_id"], body["to_collection_id"])


@pytest.mark.asyncio
@pytest.mark.parametrize("fields", [{"arrow_style": "zigzag"}, {"arrow_reversed": "sideways"}])
async def test_invalid_arrow_fields_are_422(client, auth_headers, fields):
    arch_id, body = await _connector(client, auth_headers)
    resp = await client.patch(f"/api/v1/connectors/{body['id']}", json=fields,
                              headers=auth_headers)
    assert resp.status_code == 422
    c1, c2 = body["from_collection_id"], body["to_collection_id"]
    resp = await client.post(f"/api/v1/architectures/{arch_id}/connectors",
                             json={"from_collection_id": c1, "to_collection_id": c2, **fields},
                             headers=auth_headers)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_patch_needs_the_owner(client, auth_headers):
    _arch, body = await _connector(client, auth_headers)
    other = {"Authorization": f"Bearer {uuid.uuid4()}"}
    resp = await client.patch(f"/api/v1/connectors/{body['id']}",
                              json={"arrow_style": "one_way"}, headers=other)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_reversing_does_not_change_the_calculated_total(client, auth_headers):
    arch_id, body = await _connector(client, auth_headers, arrow_style="one_way")
    resp = await client.post(
        f"/api/v1/connectors/{body['id']}/sku-selection",
        json={"service_code": "AmazonEC2", "sku": "NN4EGUUQRWVYP98C",
              "pricing_term": "on_demand", "purchase_option": "not_applicable",
              "usage_quantity": "10"},
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text

    async def total():
        calc = await client.post(f"/api/v1/architectures/{arch_id}/calculate",
                                 headers=auth_headers)
        return calc.json()["total_price"]

    before = await total()
    await client.patch(f"/api/v1/connectors/{body['id']}", json={"arrow_reversed": True},
                       headers=auth_headers)
    assert await total() == before
