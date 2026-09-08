"""Integration test for the full nest/move/un-nest/reject/VPC-delete-un-nests flow
(quickstart.md, spec User Story 1)."""

import pytest


@pytest.mark.asyncio
async def test_full_nesting_lifecycle(client, auth_headers):
    # 1. Set up: an Architecture with two VPCs and one Application Component with a SKU.
    arch = await client.post(
        "/api/v1/architectures", json={"name": "Nesting Arch", "provider": "aws"}, headers=auth_headers
    )
    arch_id = arch.json()["id"]
    vpc1 = await client.post(
        f"/api/v1/architectures/{arch_id}/collections",
        json={"type": "vpc", "name": "VPC A"},
        headers=auth_headers,
    )
    vpc1_id = vpc1.json()["id"]
    vpc2 = await client.post(
        f"/api/v1/architectures/{arch_id}/collections",
        json={"type": "vpc", "name": "VPC B"},
        headers=auth_headers,
    )
    vpc2_id = vpc2.json()["id"]
    app = await client.post(
        f"/api/v1/architectures/{arch_id}/collections",
        json={"type": "application_component", "name": "Web tier"},
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

    total_before = await client.post(f"/api/v1/architectures/{arch_id}/calculate", headers=auth_headers)
    total_before_value = total_before.json()["total_price"]

    # 2. Nest into VPC A.
    nest = await client.patch(
        f"/api/v1/collections/{app_id}", json={"parent_collection_id": vpc1_id}, headers=auth_headers
    )
    assert nest.status_code == 200
    assert nest.json()["parent_collection_id"] == vpc1_id

    # 3. Price unaffected by nesting (FR-009, SC-003).
    total_after_nest = await client.post(f"/api/v1/architectures/{arch_id}/calculate", headers=auth_headers)
    assert total_after_nest.json()["total_price"] == total_before_value

    # 4. Move to VPC B.
    move = await client.patch(
        f"/api/v1/collections/{app_id}", json={"parent_collection_id": vpc2_id}, headers=auth_headers
    )
    assert move.json()["parent_collection_id"] == vpc2_id

    # 5. Un-nest.
    unnest = await client.patch(
        f"/api/v1/collections/{app_id}", json={"parent_collection_id": None}, headers=auth_headers
    )
    assert unnest.json()["parent_collection_id"] is None

    # 6. Reject nesting a VPC inside a VPC.
    reject = await client.patch(
        f"/api/v1/collections/{vpc1_id}", json={"parent_collection_id": vpc2_id}, headers=auth_headers
    )
    assert reject.status_code == 400

    # 7. Nest again, then delete the VPC — the Application Component must survive, un-nested,
    #    with its SKU intact (FR-007, SC-004).
    await client.patch(
        f"/api/v1/collections/{app_id}", json={"parent_collection_id": vpc2_id}, headers=auth_headers
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

    total_final = await client.post(f"/api/v1/architectures/{arch_id}/calculate", headers=auth_headers)
    assert total_final.json()["total_price"] == total_before_value
