"""Contract tests for the Admin architecture export (014-architecture-templates-import-export,
contracts/api.md; spec FR-012, FR-016, FR-017, FR-025)."""

from __future__ import annotations

import uuid

import pytest


async def _named_user(client, admin_headers, username: str) -> tuple[str, dict]:
    resp = await client.post(
        "/api/v1/admin/users", json={"username": username}, headers=admin_headers
    )
    user_id = resp.json()["id"]
    return user_id, {"Authorization": f"Bearer {user_id}"}


async def _architecture_with_vpc(client, headers, name: str) -> str:
    arch = await client.post("/api/v1/architectures", json={"name": name}, headers=headers)
    arch_id = arch.json()["id"]
    await client.post(
        f"/api/v1/architectures/{arch_id}/collections",
        json={"type": "vpc", "name": "VPC", "region": "us-east-1"},
        headers=headers,
    )
    return arch_id


def _user(users: list[dict], username: str) -> dict:
    return next(u for u in users if u["username"] == username)


@pytest.mark.asyncio
async def test_admin_users_include_architecture_count(client, admin_headers):
    user_id, headers = await _named_user(client, admin_headers, "counted")
    listing = await client.get("/api/v1/admin/users", headers=admin_headers)
    assert _user(listing.json(), "counted")["architecture_count"] == 0

    await _architecture_with_vpc(client, headers, "One")
    doomed = await _architecture_with_vpc(client, headers, "Two")
    await client.delete(f"/api/v1/architectures/{doomed}", headers=headers)

    listing = await client.get("/api/v1/admin/users", headers=admin_headers)
    assert _user(listing.json(), "counted")["architecture_count"] == 1


@pytest.mark.asyncio
async def test_mutation_responses_report_the_real_count(client, admin_headers):
    """Analysis finding C1: every AdminUserOut, not just the listing, carries the true count."""
    user_id, headers = await _named_user(client, admin_headers, "mutated")
    await _architecture_with_vpc(client, headers, "Kept")
    resp = await client.put(
        f"/api/v1/admin/users/{user_id}/password", json={"password": "pw"}, headers=admin_headers
    )
    assert resp.json()["architecture_count"] == 1
    resp = await client.patch(
        f"/api/v1/admin/users/{user_id}", json={"is_active": False}, headers=admin_headers
    )
    assert resp.json()["architecture_count"] == 1


@pytest.mark.asyncio
async def test_export_returns_all_live_architectures(client, admin_headers):
    user_id, headers = await _named_user(client, admin_headers, "jdoe")
    await _architecture_with_vpc(client, headers, "Web App")
    await _architecture_with_vpc(client, headers, "Data Lake")
    removed = await _architecture_with_vpc(client, headers, "Removed")
    await client.delete(f"/api/v1/architectures/{removed}", headers=headers)

    resp = await client.get(
        f"/api/v1/admin/users/{user_id}/architectures/export", headers=admin_headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["format"] == "cloud-pricing-architectures"
    assert body["format_version"] == 1
    assert body["source_username"] == "jdoe"
    assert sorted(a["name"] for a in body["architectures"]) == ["Data Lake", "Web App"]
    first = body["architectures"][0]
    assert first["collections"][0]["ref"] == "c1"
    assert "id" not in first and "is_public" not in first


@pytest.mark.asyncio
async def test_export_rejects_non_admin(client, admin_headers, auth_headers):
    user_id, _ = await _named_user(client, admin_headers, "target1")
    resp = await client.get(
        f"/api/v1/admin/users/{user_id}/architectures/export", headers=auth_headers
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_export_requires_authentication(client, admin_headers):
    user_id, _ = await _named_user(client, admin_headers, "target2")
    resp = await client.get(f"/api/v1/admin/users/{user_id}/architectures/export")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_export_unknown_or_guest_user_is_404(client, admin_headers, auth_headers):
    unknown = await client.get(
        f"/api/v1/admin/users/{uuid.uuid4()}/architectures/export", headers=admin_headers
    )
    assert unknown.status_code == 404

    # A guest identity (username IS NULL) is never an Admin-tab row.
    guest_id = auth_headers["Authorization"].removeprefix("Bearer ")
    await client.get("/api/v1/auth/me", headers=auth_headers)
    guest = await client.get(
        f"/api/v1/admin/users/{guest_id}/architectures/export", headers=admin_headers
    )
    assert guest.status_code == 404
