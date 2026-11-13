"""Admin agent settings and per-user agent fields (023, contracts/agent-api.md "Admin routes",
FR-016–FR-019, FR-022a)."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from pydantic import SecretStr

from src.agent import settings_service
from src.config import settings
from src.models.orm import AgentUsage, User

VALID = {
    "agent_enabled": True,
    "agent_provider": "ollama",
    "agent_model": "llama3.1",
    "agent_base_url": "http://localhost:11434",
    "agent_timeout_seconds": 60,
    "agent_global_monthly_cap_usd": "10.00",
    "agent_default_user_monthly_inputs": 100,
    "agent_price_per_input_token_usd": None,
    "agent_price_per_output_token_usd": None,
}


@pytest.fixture(autouse=True)
def no_key(monkeypatch):
    monkeypatch.setattr(settings, "agent_anthropic_api_key", None)
    monkeypatch.setattr(settings_service, "_ssm_api_key", None)


async def test_get_returns_effective_values_and_never_the_key(client, admin_headers,
                                                              monkeypatch):
    monkeypatch.setattr(settings, "agent_anthropic_api_key", SecretStr("sk-hidden-value"))
    response = await client.get("/api/v1/admin/agent/settings", headers=admin_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["agent_enabled"] is False and body["agent_provider"] == "ollama"
    assert body["api_key_set"] is True
    assert body["spend_this_month_usd"] == "0.00" and body["resets_on"].endswith("-01")
    assert "sk-hidden-value" not in response.text


async def test_put_saves_and_the_next_read_uses_it(client, admin_headers):
    response = await client.put("/api/v1/admin/agent/settings", json=VALID,
                                headers=admin_headers)
    assert response.status_code == 200, response.text
    assert response.json()["agent_model"] == "llama3.1"
    status = await client.get("/api/v1/admin/agent/settings", headers=admin_headers)
    assert status.json()["agent_enabled"] is True


@pytest.mark.parametrize(
    ("change", "field"),
    [
        ({"agent_global_monthly_cap_usd": "-1"}, "agent_global_monthly_cap_usd"),
        ({"agent_timeout_seconds": 0}, "agent_timeout_seconds"),
        ({"agent_timeout_seconds": 601}, "agent_timeout_seconds"),
        ({"agent_base_url": "localhost:11434"}, "agent_base_url"),
        ({"agent_model": None}, "agent_model"),
        ({"agent_provider": "scripted"}, "agent_provider"),
        ({"agent_provider": "anthropic", "agent_model": "claude-haiku-5-5"}, "agent_provider"),
    ],
)
async def test_invalid_values_are_refused_and_nothing_is_saved(client, admin_headers, change,
                                                               field):
    refused = await client.put("/api/v1/admin/agent/settings", json={**VALID, **change},
                               headers=admin_headers)
    assert refused.status_code == 422
    assert field in str(refused.json()["detail"])
    after = await client.get("/api/v1/admin/agent/settings", headers=admin_headers)
    assert after.json()["agent_enabled"] is False


async def test_hosted_provider_needs_both_rates(client, admin_headers, monkeypatch):
    monkeypatch.setattr(settings, "agent_anthropic_api_key", SecretStr("sk-x"))
    hosted = {**VALID, "agent_provider": "anthropic", "agent_model": "claude-haiku-5-5"}
    refused = await client.put("/api/v1/admin/agent/settings",
                               json={**hosted, "agent_price_per_input_token_usd": "0.0000001"},
                               headers=admin_headers)
    assert refused.status_code == 422
    assert "agent_price_per_output_token_usd" in str(refused.json()["detail"])
    ok = await client.put("/api/v1/admin/agent/settings",
                          json={**hosted, "agent_price_per_input_token_usd": "0.0000001",
                                "agent_price_per_output_token_usd": "0.0000005"},
                          headers=admin_headers)
    assert ok.status_code == 200, ok.text


async def test_switched_off_settings_can_be_saved_incomplete(client, admin_headers):
    response = await client.put(
        "/api/v1/admin/agent/settings",
        json={**VALID, "agent_enabled": False, "agent_model": None}, headers=admin_headers)
    assert response.status_code == 200


async def test_non_admins_are_refused(client, auth_headers):
    assert (await client.get("/api/v1/admin/agent/settings",
                             headers=auth_headers)).status_code == 403
    assert (await client.put("/api/v1/admin/agent/settings", json=VALID,
                             headers=auth_headers)).status_code == 403


# --- per-user fields (US6, T062) --------------------------------------------------------------


@pytest.fixture
async def member(db_session):
    user = User(id=uuid.uuid4(), username=f"m-{uuid.uuid4().hex[:6]}")
    db_session.add(user)
    await db_session.commit()
    return user


async def _row(client, admin_headers, user):
    users = (await client.get("/api/v1/admin/users", headers=admin_headers)).json()
    return next(u for u in users if u["id"] == str(user.id))


async def test_user_table_shows_agent_fields_and_usage(client, admin_headers, member,
                                                       db_session):
    db_session.add(AgentUsage(user_id=member.id, provider="ollama", model="m",
                              counts_as_input=True, cost_usd=Decimal(0)))
    await db_session.commit()
    row = await _row(client, admin_headers, member)
    assert (row["agent_enabled_for_user"], row["agent_preview_input_counter"],
            row["agent_monthly_input_limit"], row["agent_effective_monthly_limit"],
            row["agent_inputs_this_month"]) == (False, 3, None, 100, 1)


async def test_patch_updates_agent_fields(client, admin_headers, member):
    response = await client.patch(
        f"/api/v1/admin/users/{member.id}/agent",
        json={"agent_enabled_for_user": True, "agent_monthly_input_limit": 5},
        headers=admin_headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["agent_enabled_for_user"], body["agent_monthly_input_limit"],
            body["agent_effective_monthly_limit"]) == (True, 5, 5)
    cleared = await client.patch(f"/api/v1/admin/users/{member.id}/agent",
                                 json={"clear_monthly_input_limit": True},
                                 headers=admin_headers)
    assert cleared.json()["agent_monthly_input_limit"] is None


async def test_turning_the_agent_off_for_a_user_zeroes_the_preview(client, admin_headers,
                                                                   member):
    """Analysis finding I1 (a): no continuing on the preview after the Admin turns it off."""
    await client.patch(f"/api/v1/admin/users/{member.id}/agent",
                       json={"agent_enabled_for_user": True}, headers=admin_headers)
    off = await client.patch(f"/api/v1/admin/users/{member.id}/agent",
                             json={"agent_enabled_for_user": False}, headers=admin_headers)
    assert off.json()["agent_preview_input_counter"] == 0


@pytest.mark.parametrize("body", [{"agent_preview_input_counter": -1},
                                  {"agent_monthly_input_limit": -2}])
async def test_patch_refuses_negatives(client, admin_headers, member, body):
    response = await client.patch(f"/api/v1/admin/users/{member.id}/agent", json=body,
                                  headers=admin_headers)
    assert response.status_code == 422


async def test_patch_404_for_a_guest(client, admin_headers, db_session):
    guest = User(id=uuid.uuid4())
    db_session.add(guest)
    await db_session.commit()
    response = await client.patch(f"/api/v1/admin/users/{guest.id}/agent",
                                  json={"agent_enabled_for_user": True}, headers=admin_headers)
    assert response.status_code == 404
