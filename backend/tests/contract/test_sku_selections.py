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
        json={"type": "application_component", "name": "Web", "region": "us-east-1"},
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
    # 004-canvas-pricing-improvements FR-014.
    assert resp.json()["attributes"]["instanceType"] == "t3.medium"


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


@pytest.mark.asyncio
async def test_updating_one_sku_selection_does_not_reorder_its_collections_list(
    client, auth_headers
):
    """Live user report (regression): editing one Service's pricing inputs was silently
    reordering the whole list of Services in its Collection, with no relationship to what the
    user actually changed. Root cause: `Collection.sku_selections` (orm.py) had no `order_by`,
    so Postgres had no guaranteed return order at all for that relationship -- in practice it
    happened to match insertion order until an UPDATE to one row could shift the *whole list's*
    apparent order on the next fetch, purely as an artifact of physical row storage. Services
    must appear in the order they were added to the Collection, and stay there regardless of
    what gets edited later.
    """
    arch = await client.post(
        "/api/v1/architectures", json={"name": "Arch", "provider": "aws"}, headers=auth_headers
    )
    arch_id = arch.json()["id"]
    coll = await client.post(
        f"/api/v1/architectures/{arch_id}/collections",
        json={"type": "application_component", "name": "Web", "region": "us-east-1"},
        headers=auth_headers,
    )
    coll_id = coll.json()["id"]

    selection_ids = []
    for _ in range(3):
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
        selection_ids.append(created.json()["id"])

    # Edit the *first*-added selection -- the one most likely to move under the old, order-by-
    # less relationship, since it's the one whose row physically changes.
    await client.patch(
        f"/api/v1/sku-selections/{selection_ids[0]}",
        json={"usage_quantity": "999"},
        headers=auth_headers,
    )

    arch_after = await client.get(f"/api/v1/architectures/{arch_id}", headers=auth_headers)
    collection_after = next(
        c for c in arch_after.json()["collections"] if c["id"] == coll_id
    )
    assert [s["id"] for s in collection_after["sku_selections"]] == selection_ids
