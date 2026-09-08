"""Contract tests for SKU Selection endpoints (spec FR-006, FR-007). Covers POST, PATCH, and
DELETE — not just POST (broadened during implementation per the /speckit-analyze E1 finding).
"""

import pytest

# A real, known SKU from the AWS pricing data (verified during implementation to exist and
# have an on-demand price) — used so these tests exercise the real catalog reference shape.
KNOWN_SKU = "NN4EGUUQRWVYP98C"
KNOWN_SERVICE_CODE = "AmazonEC2"


async def _create_collection(client, auth_headers) -> str:
    arch = await client.post(
        "/api/v1/architectures", json={"name": "Arch", "provider": "aws"}, headers=auth_headers
    )
    coll = await client.post(
        f"/api/v1/architectures/{arch.json()['id']}/collections",
        json={"type": "application_component", "name": "Web"},
        headers=auth_headers,
    )
    return coll.json()["id"]


@pytest.mark.asyncio
async def test_add_sku_selection(client, auth_headers):
    coll_id = await _create_collection(client, auth_headers)
    resp = await client.post(
        f"/api/v1/collections/{coll_id}/sku-selections",
        json={
            "service_code": KNOWN_SERVICE_CODE,
            "sku": KNOWN_SKU,
            "pricing_term": "on_demand",
            "purchase_option": "not_applicable",
            "usage_quantity": "730",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    assert resp.json()["sku"] == KNOWN_SKU
    assert resp.json()["unit"] == "Hrs"


@pytest.mark.asyncio
async def test_add_duplicate_sku_allowed(client, auth_headers):
    """Spec Edge Cases: the same SKU may legitimately appear more than once."""
    coll_id = await _create_collection(client, auth_headers)
    payload = {
        "service_code": KNOWN_SERVICE_CODE,
        "sku": KNOWN_SKU,
        "pricing_term": "on_demand",
        "purchase_option": "not_applicable",
        "usage_quantity": "1",
    }
    r1 = await client.post(
        f"/api/v1/collections/{coll_id}/sku-selections", json=payload, headers=auth_headers
    )
    r2 = await client.post(
        f"/api/v1/collections/{coll_id}/sku-selections", json=payload, headers=auth_headers
    )
    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r1.json()["id"] != r2.json()["id"]


@pytest.mark.asyncio
async def test_update_sku_selection_pricing_inputs(client, auth_headers):
    coll_id = await _create_collection(client, auth_headers)
    created = await client.post(
        f"/api/v1/collections/{coll_id}/sku-selections",
        json={
            "service_code": KNOWN_SERVICE_CODE,
            "sku": KNOWN_SKU,
            "pricing_term": "on_demand",
            "purchase_option": "not_applicable",
            "usage_quantity": "1",
        },
        headers=auth_headers,
    )
    selection_id = created.json()["id"]

    resp = await client.patch(
        f"/api/v1/sku-selections/{selection_id}",
        json={"usage_quantity": "500"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["usage_quantity"] == "500.0000"
    assert resp.json()["unit"] == "Hrs"


@pytest.mark.asyncio
async def test_delete_sku_selection(client, auth_headers):
    coll_id = await _create_collection(client, auth_headers)
    created = await client.post(
        f"/api/v1/collections/{coll_id}/sku-selections",
        json={
            "service_code": KNOWN_SERVICE_CODE,
            "sku": KNOWN_SKU,
            "pricing_term": "on_demand",
            "purchase_option": "not_applicable",
            "usage_quantity": "1",
        },
        headers=auth_headers,
    )
    selection_id = created.json()["id"]

    resp = await client.delete(f"/api/v1/sku-selections/{selection_id}", headers=auth_headers)
    assert resp.status_code == 204

    patch_after_delete = await client.patch(
        f"/api/v1/sku-selections/{selection_id}",
        json={"usage_quantity": "1"},
        headers=auth_headers,
    )
    assert patch_after_delete.status_code == 404
