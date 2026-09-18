"""Contract tests for `/auth/*` (012-user-accounts-sharing, spec FR-014-019a)."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_me_lazily_creates_a_guest_and_reports_no_username(client, auth_headers):
    resp = await client.get("/api/v1/auth/me", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["username"] is None
    assert body["is_admin"] is False
    assert body["is_active"] is True


@pytest.mark.asyncio
async def test_deactivated_named_user_is_rejected_on_next_request(client, admin_headers):
    create = await client.post(
        "/api/v1/admin/users", json={"username": "deactivate-me"}, headers=admin_headers
    )
    user_id = create.json()["id"]
    user_headers = {"Authorization": f"Bearer {user_id}"}

    # Still active: /auth/me succeeds.
    ok = await client.get("/api/v1/auth/me", headers=user_headers)
    assert ok.status_code == 200

    await client.patch(
        f"/api/v1/admin/users/{user_id}", json={"is_active": False}, headers=admin_headers
    )

    resp = await client.get("/api/v1/auth/me", headers=user_headers)
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_check_username_reports_existence_and_password_state(client, admin_headers):
    none_yet = await client.post(
        "/api/v1/auth/check-username", json={"username": "nobody-yet"}
    )
    assert none_yet.json() == {"exists": False, "has_password": False}

    await client.post(
        "/api/v1/admin/users", json={"username": "no-password"}, headers=admin_headers
    )
    no_pw = await client.post("/api/v1/auth/check-username", json={"username": "no-password"})
    assert no_pw.json() == {"exists": True, "has_password": False}

    create = await client.post(
        "/api/v1/admin/users", json={"username": "has-password"}, headers=admin_headers
    )
    await client.put(
        f"/api/v1/admin/users/{create.json()['id']}/password",
        json={"password": "s3cret"},
        headers=admin_headers,
    )
    has_pw = await client.post("/api/v1/auth/check-username", json={"username": "has-password"})
    assert has_pw.json() == {"exists": True, "has_password": True}


@pytest.mark.asyncio
async def test_login_nonexistent_username_401(client):
    resp = await client.post(
        "/api/v1/auth/login", json={"username": "nope-does-not-exist", "password": "x"}
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_first_time_sets_password_and_logs_in(client, admin_headers):
    create = await client.post(
        "/api/v1/admin/users", json={"username": "first-login"}, headers=admin_headers
    )
    resp = await client.post(
        "/api/v1/auth/login", json={"username": "first-login", "password": "newpass"}
    )
    assert resp.status_code == 200
    assert resp.json()["id"] == create.json()["id"]
    assert resp.json()["username"] == "first-login"

    # Now that a password exists, a second, different attempt fails.
    wrong = await client.post(
        "/api/v1/auth/login", json={"username": "first-login", "password": "different"}
    )
    assert wrong.status_code == 401

    # ...and the original password now succeeds.
    right = await client.post(
        "/api/v1/auth/login", json={"username": "first-login", "password": "newpass"}
    )
    assert right.status_code == 200


@pytest.mark.asyncio
async def test_login_wrong_password_for_existing_account_401(client, admin_headers):
    create = await client.post(
        "/api/v1/admin/users", json={"username": "has-pw-2"}, headers=admin_headers
    )
    await client.put(
        f"/api/v1/admin/users/{create.json()['id']}/password",
        json={"password": "correct"},
        headers=admin_headers,
    )
    resp = await client.post(
        "/api/v1/auth/login", json={"username": "has-pw-2", "password": "wrong"}
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_deactivated_user_401(client, admin_headers):
    create = await client.post(
        "/api/v1/admin/users", json={"username": "deactivated-login"}, headers=admin_headers
    )
    user_id = create.json()["id"]
    await client.put(
        f"/api/v1/admin/users/{user_id}/password",
        json={"password": "pw"},
        headers=admin_headers,
    )
    await client.patch(
        f"/api/v1/admin/users/{user_id}", json={"is_active": False}, headers=admin_headers
    )
    resp = await client.post(
        "/api/v1/auth/login", json={"username": "deactivated-login", "password": "pw"}
    )
    assert resp.status_code == 401
