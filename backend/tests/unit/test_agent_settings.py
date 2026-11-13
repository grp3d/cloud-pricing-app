"""Effective agent settings (023-agent-foundation, research R5): the Admin's database row wins,
else the environment, else the built-in default; the API key is never part of them."""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import SecretStr

from src.agent import settings_service
from src.config import settings
from src.models.orm import AgentSettings


@pytest.fixture
def env(monkeypatch):
    def set_(**values):
        for name, value in values.items():
            monkeypatch.setattr(settings, name, value)

    monkeypatch.setattr(settings_service, "_ssm_api_key", None)
    set_(agent_anthropic_api_key=None, agent_allow_scripted_provider=False)
    return set_


async def test_built_in_defaults_when_nothing_is_set(db_session, env):
    effective = await settings_service.effective_settings(db_session)
    assert effective.enabled is False
    assert effective.provider == "ollama"
    assert effective.model is None
    assert effective.timeout_seconds == 60
    assert effective.global_monthly_cap_usd == Decimal("10")
    assert effective.default_user_monthly_inputs == 100


async def test_environment_overrides_built_in(db_session, env):
    env(agent_model="llama3.1", agent_timeout_seconds=30)
    effective = await settings_service.effective_settings(db_session)
    assert effective.model == "llama3.1"
    assert effective.timeout_seconds == 30


async def test_database_row_overrides_environment(db_session, env):
    env(agent_model="llama3.1", agent_timeout_seconds=30)
    db_session.add(AgentSettings(id=1, agent_model="qwen3", agent_enabled=True,
                                 agent_global_monthly_cap_usd=Decimal("2.50")))
    await db_session.commit()
    effective = await settings_service.effective_settings(db_session)
    assert effective.model == "qwen3"
    assert effective.enabled is True
    assert effective.global_monthly_cap_usd == Decimal("2.50")
    # Unset in the row: falls back to the environment.
    assert effective.timeout_seconds == 30


async def test_a_changed_row_applies_on_the_next_read(db_session, env):
    db_session.add(AgentSettings(id=1, agent_model="first"))
    await db_session.commit()
    assert (await settings_service.effective_settings(db_session)).model == "first"
    row = await db_session.get(AgentSettings, 1)
    row.agent_model = "second"
    await db_session.commit()
    assert (await settings_service.effective_settings(db_session)).model == "second"


def test_api_key_from_environment(env):
    assert settings_service.api_key() is None
    assert settings_service.api_key_set() is False
    env(agent_anthropic_api_key=SecretStr("sk-env"))
    assert settings_service.api_key() == "sk-env"
    assert settings_service.api_key_set() is True


def test_api_key_from_ssm_parameter_is_read_once(monkeypatch, env):
    calls = []

    def fake_parameter(name: str) -> str:
        calls.append(name)
        return "sk-from-ssm"

    env(agent_anthropic_api_key_parameter="/app/agent-key")
    monkeypatch.setattr(settings_service, "parameter_value", fake_parameter)
    settings_service.load_api_key_parameter()
    settings_service.load_api_key_parameter()
    assert settings_service.api_key() == "sk-from-ssm"
    assert calls == ["/app/agent-key"]


async def test_effective_settings_never_carry_the_key(db_session, env):
    env(agent_anthropic_api_key=SecretStr("sk-very-secret"))
    effective = await settings_service.effective_settings(db_session)
    assert "sk-very-secret" not in repr(effective)


def test_scripted_provider_needs_the_test_flag(env):
    assert settings_service.provider_allowed("scripted") is False
    assert settings_service.provider_allowed("ollama") is True
    env(agent_allow_scripted_provider=True)
    assert settings_service.provider_allowed("scripted") is True
