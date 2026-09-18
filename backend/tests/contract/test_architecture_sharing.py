"""Contract tests for architecture sharing/import (012-user-accounts-sharing,
spec FR-020-029)."""

from __future__ import annotations

import uuid

import pytest


async def _named_user_headers(client, admin_headers, username: str) -> dict[str, str]:
    create = await client.post(
        "/api/v1/admin/users", json={"username": username}, headers=admin_headers
    )
    return {"Authorization": f"Bearer {create.json()['id']}"}


@pytest.mark.asyncio
async def test_toggle_is_public_owner_only(client, admin_headers):
    owner = await _named_user_headers(client, admin_headers, "owner1")
    other = await _named_user_headers(client, admin_headers, "other1")

    create = await client.post(
        "/api/v1/architectures", json={"name": "Web App", "provider": "aws"}, headers=owner
    )
    arch_id = create.json()["id"]
    assert create.json()["is_public"] is False

    made_public = await client.patch(
        f"/api/v1/architectures/{arch_id}", json={"is_public": True}, headers=owner
    )
    assert made_public.status_code == 200
    assert made_public.json()["is_public"] is True

    made_private = await client.patch(
        f"/api/v1/architectures/{arch_id}", json={"is_public": False}, headers=owner
    )
    assert made_private.json()["is_public"] is False

    forbidden = await client.patch(
        f"/api/v1/architectures/{arch_id}", json={"is_public": True}, headers=other
    )
    assert forbidden.status_code == 404


@pytest.mark.asyncio
async def test_guest_owned_architecture_cannot_be_made_public(client, auth_headers):
    create = await client.post(
        "/api/v1/architectures", json={"name": "Guest Arch", "provider": "aws"},
        headers=auth_headers,
    )
    resp = await client.patch(
        f"/api/v1/architectures/{create.json()['id']}",
        json={"is_public": True},
        headers=auth_headers,
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_importable_grouping_and_sorting(client, admin_headers):
    admin_arch = await client.post(
        "/api/v1/architectures", json={"name": "Reference Setup", "provider": "aws"},
        headers=admin_headers,
    )
    await client.patch(
        f"/api/v1/architectures/{admin_arch.json()['id']}",
        json={"is_public": True},
        headers=admin_headers,
    )

    zed = await _named_user_headers(client, admin_headers, "zed")
    for name in ("Zed B", "Zed A"):
        created = await client.post(
            "/api/v1/architectures", json={"name": name, "provider": "aws"}, headers=zed
        )
        await client.patch(
            f"/api/v1/architectures/{created.json()['id']}",
            json={"is_public": True},
            headers=zed,
        )

    aaron = await _named_user_headers(client, admin_headers, "aaron")
    # aaron owns no public architectures — must be omitted entirely.
    await client.post(
        "/api/v1/architectures", json={"name": "Private Only", "provider": "aws"}, headers=aaron
    )

    importer = await _named_user_headers(client, admin_headers, "importer1")
    resp = await client.get("/api/v1/architectures/importable", headers=importer)
    assert resp.status_code == 200
    groups = resp.json()["groups"]

    owner_usernames = [g["owner_username"] for g in groups]
    assert owner_usernames[0] == "Admin"
    assert "aaron" not in owner_usernames
    # Every group after "Admin" is alphabetical (FR-024).
    assert owner_usernames[1:] == sorted(owner_usernames[1:], key=str.lower)

    zed_group = next(g for g in groups if g["owner_username"] == "zed")
    names = [a["name"] for a in zed_group["architectures"]]
    assert names == ["Zed A", "Zed B"]


@pytest.mark.asyncio
async def test_importable_excludes_own_architectures(client, admin_headers):
    owner = await _named_user_headers(client, admin_headers, "self-owner")
    created = await client.post(
        "/api/v1/architectures", json={"name": "Mine", "provider": "aws"}, headers=owner
    )
    await client.patch(
        f"/api/v1/architectures/{created.json()['id']}", json={"is_public": True}, headers=owner
    )

    resp = await client.get("/api/v1/architectures/importable", headers=owner)
    owner_usernames = [g["owner_username"] for g in resp.json()["groups"]]
    assert "self-owner" not in owner_usernames


@pytest.mark.asyncio
async def test_import_creates_independent_copy(client, admin_headers):
    owner = await _named_user_headers(client, admin_headers, "src-owner")
    created = await client.post(
        "/api/v1/architectures", json={"name": "Web App", "provider": "aws"}, headers=owner
    )
    arch_id = created.json()["id"]
    await client.patch(
        f"/api/v1/architectures/{arch_id}", json={"is_public": True}, headers=owner
    )

    importer = await _named_user_headers(client, admin_headers, "importer2")
    resp = await client.post(
        f"/api/v1/architectures/{arch_id}/import", json={"name": "My Web App"}, headers=importer
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "My Web App"
    assert body["id"] != arch_id

    listing = await client.get("/api/v1/architectures", headers=importer)
    assert any(a["name"] == "My Web App" for a in listing.json())


@pytest.mark.asyncio
async def test_import_nonexistent_non_public_or_own_architecture_404s(client, admin_headers):
    owner = await _named_user_headers(client, admin_headers, "priv-owner")
    private = await client.post(
        "/api/v1/architectures", json={"name": "Private", "provider": "aws"}, headers=owner
    )
    importer = await _named_user_headers(client, admin_headers, "importer3")

    not_public = await client.post(
        f"/api/v1/architectures/{private.json()['id']}/import",
        json={"name": "x"},
        headers=importer,
    )
    assert not_public.status_code == 404

    missing = await client.post(
        f"/api/v1/architectures/{uuid.uuid4()}/import", json={"name": "x"}, headers=importer
    )
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_import_rejects_guest_caller(client, admin_headers, auth_headers):
    owner = await _named_user_headers(client, admin_headers, "guest-test-owner")
    created = await client.post(
        "/api/v1/architectures", json={"name": "Shareable", "provider": "aws"}, headers=owner
    )
    await client.patch(
        f"/api/v1/architectures/{created.json()['id']}", json={"is_public": True}, headers=owner
    )

    resp = await client.post(
        f"/api/v1/architectures/{created.json()['id']}/import",
        json={"name": "x"},
        headers=auth_headers,
    )
    assert resp.status_code == 403
