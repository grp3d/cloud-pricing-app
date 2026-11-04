"""GET and PATCH /me/preferences (019, T059, contracts §7, data-model §1)."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from tests.conftest import TestSessionLocal

URL = "/api/v1/me/preferences"
CHARTS = {"providers": [{"provider": "aws", "regions": ["us-east-1", "us-west-2"]},
                        {"provider": "gcp", "regions": []}], "category": "compute"}
MOVERS = {"provider": "azure", "category": "storage", "regions": ["eastus"], "period_weeks": 13}
WORKSPACE = {"column_widths": {"col1": 240, "col3": 320}, "collapsed": {"col2": True},
             "last_provider": "gcp"}


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {uuid.uuid4()}"}


@pytest.mark.asyncio
async def test_no_row_returns_the_empty_defaults(client, auth_headers):
    resp = await client.get(URL, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == {"schema_version": 1, "data": {"migrated_from_browser": False}}


@pytest.mark.asyncio
async def test_patch_replaces_only_the_sections_sent(client, auth_headers):
    first = await client.patch(URL, json={"workspace": WORKSPACE,
                                          "trends": {"charts": CHARTS}}, headers=auth_headers)
    assert first.status_code == 200, first.text
    assert first.json()["data"] == {"migrated_from_browser": False, "workspace": WORKSPACE,
                                    "trends": {"charts": CHARTS}}

    # Movers alone: the charts section and the workspace are kept.
    second = await client.patch(URL, json={"trends": {"movers": MOVERS}}, headers=auth_headers)
    assert second.json()["data"]["trends"] == {"charts": CHARTS, "movers": MOVERS}
    assert second.json()["data"]["workspace"] == WORKSPACE

    # The charts Reset sends the defaults for its section only.
    reset = {"providers": [], "category": "all"}
    third = await client.patch(URL, json={"trends": {"charts": reset}}, headers=auth_headers)
    assert third.json()["data"]["trends"] == {"charts": reset, "movers": MOVERS}

    # A whole section replaced: keys it no longer has are gone.
    fourth = await client.patch(URL, json={"workspace": {"last_provider": "aws"},
                                           "migrated_from_browser": True}, headers=auth_headers)
    data = fourth.json()["data"]
    assert data["workspace"] == {"last_provider": "aws"}
    assert data["migrated_from_browser"] is True

    again = await client.get(URL, headers=auth_headers)
    assert again.json() == fourth.json()


@pytest.mark.asyncio
async def test_a_null_section_returns_to_defaults(client, auth_headers):
    await client.patch(URL, json={"workspace": WORKSPACE}, headers=auth_headers)
    resp = await client.patch(URL, json={"workspace": None}, headers=auth_headers)
    assert "workspace" not in resp.json()["data"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body",
    [
        {"surprise": 1},
        {"workspace": {"theme": "dark"}},
        {"workspace": {"column_widths": {"col9": 100}}},
        {"workspace": {"column_widths": {"col1": -5}}},
        {"workspace": {"last_provider": "oracle"}},
        {"trends": {"charts": {"providers": [{"provider": "aws"}], "category": "food"}}},
        {"trends": {"charts": {"providers": [], "metric": "skus_changed"}}},
        {"trends": {"movers": {"provider": "aws", "period_weeks": 2}}},
        {"trends": {"movers": {"category": "all"}}},
        {"trends": {"history": {}}},
    ],
)
async def test_unknown_keys_and_invalid_values_are_422(client, auth_headers, body):
    resp = await client.patch(URL, json=body, headers=auth_headers)
    assert resp.status_code == 422, resp.text
    assert (await client.get(URL, headers=auth_headers)).json()["data"] == {
        "migrated_from_browser": False
    }


@pytest.mark.asyncio
async def test_users_are_isolated(client):
    alice, bob, guest = _headers(), _headers(), _headers()
    await client.patch(URL, json={"trends": {"charts": CHARTS}}, headers=alice)
    await client.patch(URL, json={"trends": {"movers": MOVERS}}, headers=guest)
    assert (await client.get(URL, headers=alice)).json()["data"]["trends"] == {"charts": CHARTS}
    assert (await client.get(URL, headers=guest)).json()["data"]["trends"] == {"movers": MOVERS}
    assert "trends" not in (await client.get(URL, headers=bob)).json()["data"]


@pytest.mark.asyncio
async def test_a_second_session_of_the_same_user_sees_the_same_record(client, auth_headers):
    await client.patch(URL, json={"trends": {"charts": CHARTS}}, headers=auth_headers)
    second_session = {"Authorization": auth_headers["Authorization"]}
    assert (await client.get(URL, headers=second_session)).json()["data"]["trends"] == {
        "charts": CHARTS
    }


@pytest.mark.asyncio
async def test_deleting_a_guest_deletes_its_preferences(client):
    guest = _headers()
    await client.patch(URL, json={"workspace": WORKSPACE}, headers=guest)
    guest_id = guest["Authorization"].removeprefix("Bearer ")
    async with TestSessionLocal() as session:
        await session.execute(text("DELETE FROM users WHERE id = :id"), {"id": guest_id})
        await session.commit()
        count = await session.scalar(
            text("SELECT count(*) FROM user_preferences WHERE user_id = :id"), {"id": guest_id}
        )
    assert count == 0


@pytest.mark.asyncio
async def test_requires_an_identity(client):
    assert (await client.get(URL)).status_code == 401
