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


# --- 021: GET /architectures/importable?provider= (contracts/api.md §2, research R12) -------


async def _public(client, headers, name: str, provider: str) -> None:
    created = await client.post(
        "/api/v1/architectures",
        json={"name": name, "provider": provider},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    await client.patch(
        f"/api/v1/architectures/{created.json()['id']}",
        json={"is_public": True},
        headers=headers,
    )


def _names(resp) -> set[str]:
    return {a["name"] for g in resp.json()["groups"] for a in g["architectures"]}


@pytest.mark.asyncio
async def test_importable_filters_by_provider(client, admin_headers):
    sharer = await _named_user_headers(client, admin_headers, "sharer-021")
    await _public(client, sharer, "AWS Shared", "aws")
    await _public(client, sharer, "GCP Shared", "gcp")
    importer = await _named_user_headers(client, admin_headers, "importer-021")

    gcp = await client.get(
        "/api/v1/architectures/importable?provider=gcp", headers=importer
    )
    assert gcp.status_code == 200, gcp.text
    assert _names(gcp) == {"GCP Shared"}
    assert [g["owner_username"] for g in gcp.json()["groups"]] == ["sharer-021"]

    everything = await client.get("/api/v1/architectures/importable", headers=importer)
    assert {"AWS Shared", "GCP Shared"} <= _names(everything)


@pytest.mark.asyncio
async def test_importable_provider_with_none_is_empty(client, admin_headers):
    sharer = await _named_user_headers(client, admin_headers, "aws-only-021")
    await _public(client, sharer, "Only AWS", "aws")
    importer = await _named_user_headers(client, admin_headers, "importer2-021")
    resp = await client.get(
        "/api/v1/architectures/importable?provider=azure", headers=importer
    )
    assert resp.status_code == 200
    assert resp.json() == {"groups": []}


@pytest.mark.asyncio
async def test_importable_unknown_provider_is_422(client, admin_headers):
    importer = await _named_user_headers(client, admin_headers, "importer3-021")
    resp = await client.get(
        "/api/v1/architectures/importable?provider=oracle", headers=importer
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_rename_owner_only_and_keeps_is_public(client, admin_headers):
    """021 (FR-043): PATCH with a name renames; only the fields sent change."""
    owner = await _named_user_headers(client, admin_headers, "renamer1")
    other = await _named_user_headers(client, admin_headers, "renamer2")
    arch_id = (
        await client.post(
            "/api/v1/architectures",
            json={"name": "Web App", "provider": "aws"},
            headers=owner,
        )
    ).json()["id"]
    await client.patch(
        f"/api/v1/architectures/{arch_id}", json={"is_public": True}, headers=owner
    )

    renamed = await client.patch(
        f"/api/v1/architectures/{arch_id}",
        json={"name": "  Shop Front  "},
        headers=owner,
    )
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Shop Front"
    assert renamed.json()["is_public"] is True

    detail = await client.get(f"/api/v1/architectures/{arch_id}", headers=owner)
    assert detail.json()["name"] == "Shop Front"

    not_owner = await client.patch(
        f"/api/v1/architectures/{arch_id}", json={"name": "Hijacked"}, headers=other
    )
    assert not_owner.status_code == 404


@pytest.mark.asyncio
async def test_guest_can_rename_own_architecture(client, auth_headers):
    arch_id = (
        await client.post(
            "/api/v1/architectures",
            json={"name": "Draft", "provider": "aws"},
            headers=auth_headers,
        )
    ).json()["id"]
    renamed = await client.patch(
        f"/api/v1/architectures/{arch_id}", json={"name": "Final"}, headers=auth_headers
    )
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Final"


@pytest.mark.parametrize(
    "body", [{}, {"name": ""}, {"name": "   "}, {"name": "x" * 256}]
)
@pytest.mark.asyncio
async def test_rename_rejects_bad_bodies(client, auth_headers, body):
    arch_id = (
        await client.post(
            "/api/v1/architectures",
            json={"name": "Keep", "provider": "aws"},
            headers=auth_headers,
        )
    ).json()["id"]
    bad = await client.patch(
        f"/api/v1/architectures/{arch_id}", json=body, headers=auth_headers
    )
    assert bad.status_code == 422
    detail = await client.get(f"/api/v1/architectures/{arch_id}", headers=auth_headers)
    assert detail.json()["name"] == "Keep"
