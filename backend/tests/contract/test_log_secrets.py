"""No secrets in the logs (017-structured-json-logging, FR-010, SC-004): the flows that carry
passwords and bearer tokens never put them, their hashes or the authorization header in a
record."""

from __future__ import annotations

import json

import pytest

ADMIN_SET_PASSWORD = "admin-set-Pa55word"
FIRST_LOGIN_PASSWORD = "first-login-Pa55word"
WRONG_PASSWORD = "wrong-Pa55word"


@pytest.mark.asyncio
async def test_auth_and_password_flows_log_no_secrets(client, admin_headers, log_output):
    # An admin creates a user and sets its password; the user logs in, fails once, and makes
    # an authenticated request with its bearer token.
    created = await client.post(
        "/api/v1/admin/users", json={"username": "secret-check"}, headers=admin_headers
    )
    user_id = created.json()["id"]
    await client.put(
        f"/api/v1/admin/users/{user_id}/password",
        json={"password": ADMIN_SET_PASSWORD},
        headers=admin_headers,
    )
    login = await client.post(
        "/api/v1/auth/login", json={"username": "secret-check", "password": ADMIN_SET_PASSWORD}
    )
    assert login.status_code == 200
    wrong = await client.post(
        "/api/v1/auth/login", json={"username": "secret-check", "password": WRONG_PASSWORD}
    )
    assert wrong.status_code == 401

    # A first login sets the password as it logs in.
    await client.post(
        "/api/v1/admin/users", json={"username": "secret-first"}, headers=admin_headers
    )
    first = await client.post(
        "/api/v1/auth/login", json={"username": "secret-first", "password": FIRST_LOGIN_PASSWORD}
    )
    assert first.status_code == 200

    token = login.json()["id"]  # this app's bearer token is the user's id
    me = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200

    rendered = "\n".join(json.dumps(r) for r in log_output())
    assert rendered  # the flows above were logged
    for secret in (ADMIN_SET_PASSWORD, FIRST_LOGIN_PASSWORD, WRONG_PASSWORD, "pbkdf2_sha256$"):
        assert secret not in rendered
    # The user id itself legitimately appears in admin paths; the header form never may.
    assert f"bearer {token}".lower() not in rendered.lower()
    assert "bearer " not in rendered.lower()
    assert "authorization" not in rendered.lower()
