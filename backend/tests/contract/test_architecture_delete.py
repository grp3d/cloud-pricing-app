"""Contract test for DELETE /architectures/{id} — soft delete + idempotency (spec FR-014)."""

import pytest


@pytest.mark.asyncio
async def test_soft_delete_is_idempotent_and_hides_from_list(client, auth_headers):
    create = await client.post(
        "/api/v1/architectures", json={"name": "ToDelete", "provider": "aws"}, headers=auth_headers
    )
    arch_id = create.json()["id"]

    resp1 = await client.delete(f"/api/v1/architectures/{arch_id}", headers=auth_headers)
    assert resp1.status_code == 204

    resp2 = await client.delete(f"/api/v1/architectures/{arch_id}", headers=auth_headers)
    assert resp2.status_code == 204

    listing = await client.get("/api/v1/architectures?provider=aws", headers=auth_headers)
    assert all(a["id"] != arch_id for a in listing.json())

    # Confirmation prompt is a frontend concern; the API itself just enforces the soft delete.
    detail = await client.get(f"/api/v1/architectures/{arch_id}", headers=auth_headers)
    assert detail.status_code == 404
