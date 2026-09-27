"""Contract tests for SKU Selection endpoints (spec FR-006, FR-007). Covers POST, PATCH, and
DELETE — not just POST (broadened during implementation per the /speckit-analyze E1 finding).
"""

import uuid

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
    # 015-canvas-service-icons, contracts/api.md.
    assert resp.json()["product_family"] == "Compute Instance"


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
    assert resp.json()["product_family"] == "Compute Instance"  # 015, contracts/api.md


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


# --- 016-canvas-icon-layout, FR-004a/FR-004b, contracts/api.md §2: move a service to another box --


async def _architecture(client, headers) -> str:
    resp = await client.post(
        "/api/v1/architectures", json={"name": "Move", "provider": "aws"}, headers=headers
    )
    return resp.json()["id"]


async def _box(client, headers, arch_id: str, name: str, region: str = "us-east-1") -> str:
    resp = await client.post(
        f"/api/v1/architectures/{arch_id}/collections",
        json={"type": "application_component", "name": name, "region": region},
        headers=headers,
    )
    return resp.json()["id"]


async def _service(client, headers, collection_id: str) -> str:
    resp = await client.post(
        f"/api/v1/collections/{collection_id}/sku-selections",
        json={
            "service_code": KNOWN_SERVICE_CODE,
            "sku": KNOWN_SKU,
            "pricing_term": "on_demand",
            "purchase_option": "not_applicable",
            "usage_quantity": "1",
        },
        headers=headers,
    )
    return resp.json()["id"]


def _box_of(detail: dict, selection_id: str) -> str | None:
    for collection in detail["collections"]:
        if any(s["id"] == selection_id for s in collection["sku_selections"]):
            return collection["id"]
    return None


@pytest.mark.asyncio
async def test_move_service_to_same_region_box(client, auth_headers):
    arch_id = await _architecture(client, auth_headers)
    source = await _box(client, auth_headers, arch_id, "Web")
    target = await _box(client, auth_headers, arch_id, "App")
    selection_id = await _service(client, auth_headers, source)

    resp = await client.patch(
        f"/api/v1/sku-selections/{selection_id}",
        json={"collection_id": target},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    detail = (await client.get(f"/api/v1/architectures/{arch_id}", headers=auth_headers)).json()
    assert _box_of(detail, selection_id) == target


@pytest.mark.asyncio
async def test_move_service_to_other_region_is_refused(client, auth_headers):
    arch_id = await _architecture(client, auth_headers)
    source = await _box(client, auth_headers, arch_id, "Web", "us-east-1")
    target = await _box(client, auth_headers, arch_id, "App", "eu-west-1")
    selection_id = await _service(client, auth_headers, source)

    resp = await client.patch(
        f"/api/v1/sku-selections/{selection_id}",
        json={"collection_id": target},
        headers=auth_headers,
    )
    assert resp.status_code == 409
    assert resp.json()["error"] == "region_mismatch"
    detail = (await client.get(f"/api/v1/architectures/{arch_id}", headers=auth_headers)).json()
    assert _box_of(detail, selection_id) == source


@pytest.mark.asyncio
async def test_move_service_to_other_architecture_is_not_found(client, auth_headers):
    arch_id = await _architecture(client, auth_headers)
    other_arch = await _architecture(client, auth_headers)
    source = await _box(client, auth_headers, arch_id, "Web")
    target = await _box(client, auth_headers, other_arch, "Elsewhere")
    selection_id = await _service(client, auth_headers, source)

    resp = await client.patch(
        f"/api/v1/sku-selections/{selection_id}",
        json={"collection_id": target},
        headers=auth_headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_move_service_into_another_users_box_is_not_found(client, auth_headers):
    other_headers = {"Authorization": f"Bearer {uuid.uuid4()}"}
    arch_id = await _architecture(client, auth_headers)
    source = await _box(client, auth_headers, arch_id, "Web")
    foreign = await _box(client, other_headers, await _architecture(client, other_headers), "X")
    selection_id = await _service(client, auth_headers, source)

    resp = await client.patch(
        f"/api/v1/sku-selections/{selection_id}",
        json={"collection_id": foreign},
        headers=auth_headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_connector_service_cannot_be_moved_to_a_box(client, auth_headers):
    arch_id = await _architecture(client, auth_headers)
    a = await _box(client, auth_headers, arch_id, "A")
    b = await _box(client, auth_headers, arch_id, "B")
    conn = await client.post(
        f"/api/v1/architectures/{arch_id}/connectors",
        json={"from_collection_id": a, "to_collection_id": b},
        headers=auth_headers,
    )
    attached = await client.post(
        f"/api/v1/connectors/{conn.json()['id']}/sku-selection",
        json={
            "service_code": KNOWN_SERVICE_CODE,
            "sku": KNOWN_SKU,
            "pricing_term": "on_demand",
            "purchase_option": "not_applicable",
            "usage_quantity": "1",
        },
        headers=auth_headers,
    )

    resp = await client.patch(
        f"/api/v1/sku-selections/{attached.json()['id']}",
        json={"collection_id": a},
        headers=auth_headers,
    )
    assert resp.status_code == 400
    assert resp.json()["error"] == "not_movable"


@pytest.mark.asyncio
async def test_move_service_to_its_own_box_changes_nothing(client, auth_headers):
    arch_id = await _architecture(client, auth_headers)
    source = await _box(client, auth_headers, arch_id, "Web")
    selection_id = await _service(client, auth_headers, source)

    resp = await client.patch(
        f"/api/v1/sku-selections/{selection_id}",
        json={"collection_id": source},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    detail = (await client.get(f"/api/v1/architectures/{arch_id}", headers=auth_headers)).json()
    assert _box_of(detail, selection_id) == source


# --- 017-structured-json-logging, FR-008 e: move log events ---------------------------------


def _move_events(log_output, message: str) -> list[dict]:
    return [r for r in log_output() if r["message"] == message]


@pytest.mark.asyncio
async def test_move_logs_service_moved(client, auth_headers, log_output):
    arch_id = await _architecture(client, auth_headers)
    source = await _box(client, auth_headers, arch_id, "Web", "us-east-1")
    target = await _box(client, auth_headers, arch_id, "App", "us-east-1")
    selection_id = await _service(client, auth_headers, source)

    resp = await client.patch(
        f"/api/v1/sku-selections/{selection_id}",
        json={"collection_id": target},
        headers=auth_headers,
    )

    [record] = _move_events(log_output, "service moved")
    assert record["level"] == "info"
    assert record["sku_selection_id"] == selection_id
    assert record["sku"] == KNOWN_SKU
    assert record["service_code"] == KNOWN_SERVICE_CODE
    assert record["source_collection_id"] == source
    assert record["target_collection_id"] == target
    assert record["request_id"] == resp.headers["X-Request-ID"]


@pytest.mark.asyncio
async def test_region_mismatch_logs_service_move_refused(client, auth_headers, log_output):
    arch_id = await _architecture(client, auth_headers)
    source = await _box(client, auth_headers, arch_id, "Web", "us-east-1")
    target = await _box(client, auth_headers, arch_id, "App", "eu-west-1")
    selection_id = await _service(client, auth_headers, source)

    await client.patch(
        f"/api/v1/sku-selections/{selection_id}",
        json={"collection_id": target},
        headers=auth_headers,
    )

    [record] = _move_events(log_output, "service move refused")
    assert record["level"] == "warning"
    assert record["reason"] == "region_mismatch"
    assert record["sku_selection_id"] == selection_id
    assert record["sku"] == KNOWN_SKU
    assert record["service_code"] == KNOWN_SERVICE_CODE
    assert record["source_collection_id"] == source
    assert record["target_collection_id"] == target
    assert _move_events(log_output, "service moved") == []


@pytest.mark.asyncio
async def test_connector_service_logs_not_movable(client, auth_headers, log_output):
    arch_id = await _architecture(client, auth_headers)
    a = await _box(client, auth_headers, arch_id, "A")
    b = await _box(client, auth_headers, arch_id, "B")
    conn = await client.post(
        f"/api/v1/architectures/{arch_id}/connectors",
        json={"from_collection_id": a, "to_collection_id": b},
        headers=auth_headers,
    )
    attached = await client.post(
        f"/api/v1/connectors/{conn.json()['id']}/sku-selection",
        json={
            "service_code": KNOWN_SERVICE_CODE,
            "sku": KNOWN_SKU,
            "pricing_term": "on_demand",
            "purchase_option": "not_applicable",
            "usage_quantity": "1",
        },
        headers=auth_headers,
    )

    await client.patch(
        f"/api/v1/sku-selections/{attached.json()['id']}",
        json={"collection_id": a},
        headers=auth_headers,
    )

    [record] = _move_events(log_output, "service move refused")
    assert record["reason"] == "not_movable"
    assert record["source_collection_id"] is None
    assert record["target_collection_id"] == a
