"""Contract tests for `/admin/users` (012-user-accounts-sharing, spec FR-004-013)."""

from __future__ import annotations

import uuid

import pytest


@pytest.mark.asyncio
async def test_non_admin_is_rejected(client, auth_headers):
    resp = await client.get("/api/v1/admin/users", headers=auth_headers)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_create_user_defaults_active_no_password(client, admin_headers):
    resp = await client.post(
        "/api/v1/admin/users", json={"username": "alice"}, headers=admin_headers
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["username"] == "alice"
    assert body["is_active"] is True
    assert body["has_password"] is False
    assert body["password_hash_suffix"] is None
    assert body["is_admin"] is False
    assert body["is_default_admin"] is False


@pytest.mark.asyncio
async def test_create_duplicate_username_rejected(client, admin_headers):
    await client.post("/api/v1/admin/users", json={"username": "bob"}, headers=admin_headers)
    dup = await client.post("/api/v1/admin/users", json={"username": "bob"}, headers=admin_headers)
    assert dup.status_code == 400


@pytest.mark.asyncio
async def test_list_only_includes_named_users(client, admin_headers, auth_headers):
    # `auth_headers` lazily creates a guest (username IS NULL) — must never appear.
    await client.get("/api/v1/auth/me", headers=auth_headers)
    await client.post("/api/v1/admin/users", json={"username": "carol"}, headers=admin_headers)

    resp = await client.get("/api/v1/admin/users", headers=admin_headers)
    usernames = [u["username"] for u in resp.json()]
    assert "carol" in usernames
    assert "Admin" in usernames
    assert None not in usernames


@pytest.mark.asyncio
async def test_set_password_updates_hash_suffix_and_has_password(client, admin_headers):
    create = await client.post(
        "/api/v1/admin/users", json={"username": "dave"}, headers=admin_headers
    )
    user_id = create.json()["id"]

    first = await client.put(
        f"/api/v1/admin/users/{user_id}/password",
        json={"password": "pw-one"},
        headers=admin_headers,
    )
    assert first.status_code == 200
    assert first.json()["has_password"] is True
    first_suffix = first.json()["password_hash_suffix"]
    assert first_suffix is not None

    second = await client.put(
        f"/api/v1/admin/users/{user_id}/password",
        json={"password": "a-totally-different-password"},
        headers=admin_headers,
    )
    assert second.json()["password_hash_suffix"] != first_suffix


@pytest.mark.asyncio
async def test_toggle_active(client, admin_headers):
    create = await client.post(
        "/api/v1/admin/users", json={"username": "erin"}, headers=admin_headers
    )
    user_id = create.json()["id"]

    off = await client.patch(
        f"/api/v1/admin/users/{user_id}", json={"is_active": False}, headers=admin_headers
    )
    assert off.status_code == 200
    assert off.json()["is_active"] is False

    on = await client.patch(
        f"/api/v1/admin/users/{user_id}", json={"is_active": True}, headers=admin_headers
    )
    assert on.json()["is_active"] is True


@pytest.mark.asyncio
async def test_default_admin_cannot_be_deactivated_or_purged(client, admin_headers):
    me = await client.get("/api/v1/auth/me", headers=admin_headers)
    admin_id = me.json()["id"]

    patch_resp = await client.patch(
        f"/api/v1/admin/users/{admin_id}", json={"is_active": False}, headers=admin_headers
    )
    assert patch_resp.status_code == 403

    delete_resp = await client.delete(f"/api/v1/admin/users/{admin_id}", headers=admin_headers)
    assert delete_resp.status_code == 403


@pytest.mark.asyncio
async def test_purge_removes_only_target_user_and_their_data(client, admin_headers):
    await client.post("/api/v1/admin/users", json={"username": "keep-me"}, headers=admin_headers)
    remove = await client.post(
        "/api/v1/admin/users", json={"username": "remove-me"}, headers=admin_headers
    )
    remove_headers = {"Authorization": f"Bearer {remove.json()['id']}"}
    await client.post(
        "/api/v1/architectures",
        json={"name": "Doomed Arch", "provider": "aws"},
        headers=remove_headers,
    )

    resp = await client.delete(
        f"/api/v1/admin/users/{remove.json()['id']}", headers=admin_headers
    )
    assert resp.status_code == 204

    listing = await client.get("/api/v1/admin/users", headers=admin_headers)
    usernames = [u["username"] for u in listing.json()]
    assert "remove-me" not in usernames
    assert "keep-me" in usernames

    # The purged user's own token now resolves to a brand-new (re-created) guest identity —
    # its architecture list is empty, not an error, and definitely not "Doomed Arch."
    archs = await client.get("/api/v1/architectures", headers=remove_headers)
    assert archs.json() == []


@pytest.mark.asyncio
async def test_nonexistent_or_guest_user_id_404s(client, admin_headers):
    resp = await client.patch(
        f"/api/v1/admin/users/{uuid.uuid4()}", json={"is_active": False}, headers=admin_headers
    )
    assert resp.status_code == 404
