"""Contract tests for the Admin architecture import (014-architecture-templates-import-export,
contracts/api.md; spec FR-018-FR-025)."""

from __future__ import annotations

import uuid

import pytest

KNOWN_SKU = "NN4EGUUQRWVYP98C"  # us-east-1 AmazonEC2, present in the pricing fixture


def _entry(name: str, sku: str = KNOWN_SKU) -> dict:
    return {
        "name": name,
        "provider": "aws",
        "collections": [
            {
                "ref": "c1",
                "type": "vpc",
                "name": "VPC (us-east-1)",
                "region": "us-east-1",
                "sku_selections": [
                    {
                        "service_code": "AmazonEC2",
                        "sku": sku,
                        "pricing_term": "on_demand",
                        "purchase_option": "not_applicable",
                        "usage_quantity": 24,
                    }
                ],
            }
        ],
        "connectors": [],
    }


def _doc(*entries, **overrides) -> dict:
    doc = {
        "format": "cloud-pricing-architectures",
        "format_version": 1,
        "exported_at": "2026-09-25T14:30:22Z",
        "source_username": "jdoe",
        "architectures": list(entries),
    }
    doc.update(overrides)
    return doc


async def _named_user(client, admin_headers, username: str) -> tuple[str, dict]:
    resp = await client.post(
        "/api/v1/admin/users", json={"username": username}, headers=admin_headers
    )
    user_id = resp.json()["id"]
    return user_id, {"Authorization": f"Bearer {user_id}"}


def _url(user_id: str) -> str:
    return f"/api/v1/admin/users/{user_id}/architectures/import"


@pytest.mark.asyncio
async def test_mixed_file_imports_valid_entries_privately(client, admin_headers):
    user_id, headers = await _named_user(client, admin_headers, "importer")
    await client.post("/api/v1/architectures", json={"name": "Existing"}, headers=headers)

    resp = await client.post(
        _url(user_id),
        json=_doc(_entry("New One"), _entry("Existing"), _entry("Bad", sku="ZZZZZZZZZZZZZZZZ")),
        headers=admin_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert (body["imported_count"], body["failed_count"]) == (1, 2)
    assert [(r["name"], r["status"]) for r in body["results"]] == [
        ("New One", "success"),
        ("Existing", "failed"),
        ("Bad", "failed"),
    ]
    assert body["results"][1]["error"] == "Architecture name already exists"
    assert body["results"][2]["error"].startswith("Service not found in pricing data:")

    mine = await client.get("/api/v1/architectures?provider=aws", headers=headers)
    imported = next(a for a in mine.json() if a["name"] == "New One")
    assert imported["is_public"] is False


@pytest.mark.asyncio
async def test_import_into_the_admins_own_row(client, admin_headers):
    admin_id = admin_headers["Authorization"].removeprefix("Bearer ")
    resp = await client.post(
        _url(admin_id), json=_doc(_entry(f"Admin copy {uuid.uuid4().hex[:6]}")),
        headers=admin_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["results"][0]["status"] == "success"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "doc",
    [
        _doc(format="something-else"),
        _doc(format_version=2),
        {k: v for k, v in _doc().items() if k != "architectures"},
        _doc(architectures={"not": "a list"}),
        # The old baseline JSON shape from docs/functionality_2026-09-25.md (no `format`).
        {"version": "1.0", "architectures": [{"id": "arch_x", "components": []}]},
    ],
)
async def test_whole_file_problems_are_400(client, admin_headers, doc):
    """Analysis finding C2: every whole-file problem is this API's own 400, never a 422."""
    user_id, _ = await _named_user(client, admin_headers, f"bad-{uuid.uuid4().hex[:6]}")
    resp = await client.post(_url(user_id), json=doc, headers=admin_headers)
    assert resp.status_code == 400
    assert resp.json()["error"] == "invalid_import_file"
    assert resp.json()["message"]


@pytest.mark.asyncio
async def test_non_object_body_is_422(client, admin_headers):
    user_id, _ = await _named_user(client, admin_headers, "arrayed")
    resp = await client.post(_url(user_id), json=[1, 2, 3], headers=admin_headers)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_non_admin_forbidden(client, admin_headers, auth_headers):
    user_id, _ = await _named_user(client, admin_headers, "target3")
    resp = await client.post(_url(user_id), json=_doc(), headers=auth_headers)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_unauthenticated(client, admin_headers):
    user_id, _ = await _named_user(client, admin_headers, "target4")
    resp = await client.post(_url(user_id), json=_doc())
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_unknown_or_guest_target_is_404(client, admin_headers, auth_headers):
    unknown = await client.post(_url(str(uuid.uuid4())), json=_doc(), headers=admin_headers)
    assert unknown.status_code == 404
    guest_id = auth_headers["Authorization"].removeprefix("Bearer ")
    await client.get("/api/v1/auth/me", headers=auth_headers)
    guest = await client.post(_url(guest_id), json=_doc(), headers=admin_headers)
    assert guest.status_code == 404


@pytest.mark.asyncio
async def test_imported_architecture_is_not_in_the_public_import_list(
    client, admin_headers, auth_headers
):
    """FR-023/FR-024: an Admin-imported copy is private, so the 012 Import list never shows it."""
    user_id, _ = await _named_user(client, admin_headers, "privately")
    await client.post(_url(user_id), json=_doc(_entry("Hidden")), headers=admin_headers)
    listing = await client.get("/api/v1/architectures/importable", headers=auth_headers)
    names = [a["name"] for g in listing.json()["groups"] for a in g["architectures"]]
    assert "Hidden" not in names
