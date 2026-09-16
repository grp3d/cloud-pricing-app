"""Integration test for the full nest/move/un-nest/reject/VPC-delete-un-nests flow
(quickstart.md, spec User Story 1)."""

import pytest


@pytest.mark.asyncio
async def test_full_nesting_lifecycle(client, auth_headers):
    # 1. Set up: an Architecture with two VPCs and one Application Component with a SKU.
    arch = await client.post(
        "/api/v1/architectures",
        json={"name": "Nesting Arch", "provider": "aws"},
        headers=auth_headers,
    )
    arch_id = arch.json()["id"]
    vpc1 = await client.post(
        f"/api/v1/architectures/{arch_id}/collections",
        json={"type": "vpc", "name": "VPC A", "region": "us-east-1"},
        headers=auth_headers,
    )
    vpc1_id = vpc1.json()["id"]
    vpc2 = await client.post(
        f"/api/v1/architectures/{arch_id}/collections",
        json={"type": "vpc", "name": "VPC B", "region": "us-east-1"},
        headers=auth_headers,
    )
    vpc2_id = vpc2.json()["id"]
    app = await client.post(
        f"/api/v1/architectures/{arch_id}/collections",
        json={"type": "application_component", "name": "Web tier", "region": "us-east-1"},
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
            "usage_quantity": "730",
        },
        headers=auth_headers,
    )

    total_before = await client.post(
        f"/api/v1/architectures/{arch_id}/calculate", headers=auth_headers
    )
    total_before_value = total_before.json()["total_price"]

    # 2. Nest into VPC A.
    nest = await client.patch(
        f"/api/v1/collections/{app_id}",
        json={"parent_collection_id": vpc1_id},
        headers=auth_headers,
    )
    assert nest.status_code == 200
    assert nest.json()["parent_collection_id"] == vpc1_id

    # 3. Price unaffected by nesting (FR-009, SC-003).
    total_after_nest = await client.post(
        f"/api/v1/architectures/{arch_id}/calculate", headers=auth_headers
    )
    assert total_after_nest.json()["total_price"] == total_before_value

    # 4. Move to VPC B.
    move = await client.patch(
        f"/api/v1/collections/{app_id}",
        json={"parent_collection_id": vpc2_id},
        headers=auth_headers,
    )
    assert move.json()["parent_collection_id"] == vpc2_id

    # 5. Un-nest.
    unnest = await client.patch(
        f"/api/v1/collections/{app_id}", json={"parent_collection_id": None}, headers=auth_headers
    )
    assert unnest.json()["parent_collection_id"] is None

    # 6. Reject nesting a VPC inside a VPC.
    reject = await client.patch(
        f"/api/v1/collections/{vpc1_id}",
        json={"parent_collection_id": vpc2_id},
        headers=auth_headers,
    )
    assert reject.status_code == 400

    # 7. Nest again, then delete the VPC — the Application Component must survive, un-nested,
    #    with its SKU intact (FR-007, SC-004).
    await client.patch(
        f"/api/v1/collections/{app_id}",
        json={"parent_collection_id": vpc2_id},
        headers=auth_headers,
    )
    delete_resp = await client.delete(f"/api/v1/collections/{vpc2_id}", headers=auth_headers)
    assert delete_resp.status_code == 204

    detail = await client.get(f"/api/v1/architectures/{arch_id}", headers=auth_headers)
    body = detail.json()
    surviving = next(c for c in body["collections"] if c["id"] == app_id)
    assert surviving["parent_collection_id"] is None
    assert len(surviving["sku_selections"]) == 1
    assert surviving["sku_selections"][0]["sku"] == "NN4EGUUQRWVYP98C"
    # VPC B itself is gone from the active list (soft-deleted).
    assert all(c["id"] != vpc2_id for c in body["collections"])

    total_final = await client.post(
        f"/api/v1/architectures/{arch_id}/calculate", headers=auth_headers
    )
    assert total_final.json()["total_price"] == total_before_value


@pytest.mark.asyncio
async def test_deleting_a_nested_app_component_does_not_affect_its_vpc_or_siblings(
    client, auth_headers
):
    """spec FR-008: deleting a nested Application Component behaves the same as deleting a
    top-level one — its VPC and any sibling nested inside the same VPC are unaffected."""
    arch = await client.post(
        "/api/v1/architectures",
        json={"name": "Delete Nested Arch", "provider": "aws"},
        headers=auth_headers,
    )
    arch_id = arch.json()["id"]
    vpc = await client.post(
        f"/api/v1/architectures/{arch_id}/collections",
        json={"type": "vpc", "name": "VPC", "region": "us-east-1"},
        headers=auth_headers,
    )
    vpc_id = vpc.json()["id"]
    app1 = await client.post(
        f"/api/v1/architectures/{arch_id}/collections",
        json={"type": "application_component", "name": "App 1", "region": "us-east-1"},
        headers=auth_headers,
    )
    app1_id = app1.json()["id"]
    app2 = await client.post(
        f"/api/v1/architectures/{arch_id}/collections",
        json={"type": "application_component", "name": "App 2", "region": "us-east-1"},
        headers=auth_headers,
    )
    app2_id = app2.json()["id"]
    for app_id in (app1_id, app2_id):
        await client.patch(
            f"/api/v1/collections/{app_id}",
            json={"parent_collection_id": vpc_id},
            headers=auth_headers,
        )

    delete_resp = await client.delete(f"/api/v1/collections/{app1_id}", headers=auth_headers)
    assert delete_resp.status_code == 204

    detail = await client.get(f"/api/v1/architectures/{arch_id}", headers=auth_headers)
    body = detail.json()
    ids = {c["id"] for c in body["collections"]}
    assert app1_id not in ids  # deleted
    assert vpc_id in ids  # VPC unaffected
    assert app2_id in ids  # sibling unaffected
    sibling = next(c for c in body["collections"] if c["id"] == app2_id)
    assert sibling["parent_collection_id"] == vpc_id  # sibling still nested, untouched


@pytest.mark.asyncio
async def test_data_connector_on_nested_component_survives_nest_move_unnest(client, auth_headers):
    """spec FR-010 / SC-002: a Data Connector involving a nested Application Component is
    unaffected by nesting, moving, or un-nesting that component."""
    arch = await client.post(
        "/api/v1/architectures",
        json={"name": "Connector Nesting Arch", "provider": "aws"},
        headers=auth_headers,
    )
    arch_id = arch.json()["id"]
    vpc1 = await client.post(
        f"/api/v1/architectures/{arch_id}/collections",
        json={"type": "vpc", "name": "VPC A", "region": "us-east-1"},
        headers=auth_headers,
    )
    vpc1_id = vpc1.json()["id"]
    vpc2 = await client.post(
        f"/api/v1/architectures/{arch_id}/collections",
        json={"type": "vpc", "name": "VPC B", "region": "us-east-1"},
        headers=auth_headers,
    )
    vpc2_id = vpc2.json()["id"]
    app = await client.post(
        f"/api/v1/architectures/{arch_id}/collections",
        json={"type": "application_component", "name": "Web tier", "region": "us-east-1"},
        headers=auth_headers,
    )
    app_id = app.json()["id"]

    connector = await client.post(
        f"/api/v1/architectures/{arch_id}/connectors",
        json={"from_collection_id": app_id, "to_collection_id": vpc1_id},
        headers=auth_headers,
    )
    assert connector.status_code == 201
    connector_id = connector.json()["id"]
    attach = await client.post(
        f"/api/v1/connectors/{connector_id}/sku-selection",
        json={
            "service_code": "AmazonEC2",
            "sku": "2QF2GD6XUCJHFMKF",
            "pricing_term": "on_demand",
            "purchase_option": "not_applicable",
            "usage_quantity": "10",
        },
        headers=auth_headers,
    )
    assert attach.status_code == 201

    def get_connector(body: dict) -> dict:
        return next(c for c in body["connectors"] if c["id"] == connector_id)

    # Nest, move, un-nest — the connector must be present and unchanged after each step.
    for parent_id in (vpc1_id, vpc2_id, None):
        await client.patch(
            f"/api/v1/collections/{app_id}",
            json={"parent_collection_id": parent_id},
            headers=auth_headers,
        )
        detail = await client.get(f"/api/v1/architectures/{arch_id}", headers=auth_headers)
        conn = get_connector(detail.json())
        assert conn["from_collection_id"] == app_id
        assert conn["to_collection_id"] == vpc1_id
        assert conn["sku_selection"]["sku"] == "2QF2GD6XUCJHFMKF"
