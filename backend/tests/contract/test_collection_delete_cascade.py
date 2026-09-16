"""Contract test: DELETE /collections/{id} cascades to soft-delete its Data Connectors
(spec FR-015)."""

import pytest


@pytest.mark.asyncio
async def test_deleting_collection_cascades_to_connector(client, auth_headers):
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
    conn = await client.post(
        f"/api/v1/architectures/{arch_id}/connectors",
        json={"from_collection_id": c1.json()["id"], "to_collection_id": c2.json()["id"]},
        headers=auth_headers,
    )
    assert conn.status_code == 201

    del_resp = await client.delete(f"/api/v1/collections/{c1.json()['id']}", headers=auth_headers)
    assert del_resp.status_code == 204

    detail = await client.get(f"/api/v1/architectures/{arch_id}", headers=auth_headers)
    body = detail.json()
    assert len(body["collections"]) == 1  # only VPC B remains
    assert body["connectors"] == []  # the connector was cascade-deleted
