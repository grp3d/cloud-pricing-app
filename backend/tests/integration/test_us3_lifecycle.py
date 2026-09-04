"""Integration test for User Story 3 (quickstart.md section 3): soft-delete lifecycle."""

import pytest


@pytest.mark.asyncio
async def test_soft_delete_lifecycle(client, auth_headers):
    arch1 = await client.post(
        "/api/v1/architectures", json={"name": "Keep Me", "provider": "aws"}, headers=auth_headers
    )
    arch2 = await client.post(
        "/api/v1/architectures", json={"name": "Delete Me", "provider": "aws"}, headers=auth_headers
    )

    listing = await client.get("/api/v1/architectures?provider=aws", headers=auth_headers)
    names = {a["name"] for a in listing.json()}
    assert names == {"Keep Me", "Delete Me"}

    del_resp = await client.delete(f"/api/v1/architectures/{arch2.json()['id']}", headers=auth_headers)
    assert del_resp.status_code == 204

    listing_after = await client.get("/api/v1/architectures?provider=aws", headers=auth_headers)
    names_after = {a["name"] for a in listing_after.json()}
    assert names_after == {"Keep Me"}

    # The other architecture (and its data) is untouched.
    still_there = await client.get(f"/api/v1/architectures/{arch1.json()['id']}", headers=auth_headers)
    assert still_there.status_code == 200
