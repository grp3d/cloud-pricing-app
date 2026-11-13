"""Effective agent settings (023-agent-foundation, research R5, FR-016–FR-018).

The Admin edits a single `agent_settings` row; each value left null there falls back to the
environment (`AGENT_*` in `src.config.Settings`), which has the built-in defaults. Settings are
read at the start of every message, so a change on the Admin page applies to the next message
with no redeploy.

The hosted model's API key is never stored in the database or returned by any endpoint
(FR-017, Principle VIII). It comes from `AGENT_ANTHROPIC_API_KEY`, or, in the cloud, from the
SSM parameter named by `AGENT_ANTHROPIC_API_KEY_PARAMETER`, read once at startup.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.models.orm import AgentSettings
from src.ops.params import get_parameter as parameter_value

# The key read from SSM at startup (None until `load_api_key_parameter` succeeds).
_ssm_api_key: str | None = None


@dataclass(frozen=True)
class EffectiveAgentSettings:
    enabled: bool
    provider: str
    model: str | None
    base_url: str
    timeout_seconds: int
    global_monthly_cap_usd: Decimal
    default_user_monthly_inputs: int
    price_per_input_token_usd: Decimal | None
    price_per_output_token_usd: Decimal | None


def _pick(row_value, env_value):
    return env_value if row_value is None else row_value


async def settings_row(session: AsyncSession) -> AgentSettings | None:
    return await session.get(AgentSettings, 1, populate_existing=True)


async def effective_settings(session: AsyncSession) -> EffectiveAgentSettings:
    row = await settings_row(session)
    get = (lambda name: getattr(row, name)) if row is not None else (lambda _name: None)
    return EffectiveAgentSettings(
        enabled=_pick(get("agent_enabled"), settings.agent_enabled),
        provider=_pick(get("agent_provider"), settings.agent_provider),
        model=_pick(get("agent_model"), settings.agent_model),
        base_url=_pick(get("agent_base_url"), settings.agent_base_url),
        timeout_seconds=_pick(get("agent_timeout_seconds"), settings.agent_timeout_seconds),
        global_monthly_cap_usd=Decimal(
            _pick(get("agent_global_monthly_cap_usd"), settings.agent_global_monthly_cap_usd)
        ),
        default_user_monthly_inputs=_pick(
            get("agent_default_user_monthly_inputs"), settings.agent_default_user_monthly_inputs
        ),
        price_per_input_token_usd=_pick(
            get("agent_price_per_input_token_usd"), settings.agent_price_per_input_token_usd
        ),
        price_per_output_token_usd=_pick(
            get("agent_price_per_output_token_usd"), settings.agent_price_per_output_token_usd
        ),
    )


def load_api_key_parameter() -> None:
    """Read the key from SSM once (at startup), when a parameter name is configured."""
    global _ssm_api_key
    name = settings.agent_anthropic_api_key_parameter
    if name and _ssm_api_key is None:
        _ssm_api_key = parameter_value(name)


def api_key() -> str | None:
    if settings.agent_anthropic_api_key is not None:
        return settings.agent_anthropic_api_key.get_secret_value()
    return _ssm_api_key


def api_key_set() -> bool:
    return bool(api_key())


def provider_allowed(provider: str) -> bool:
    """`scripted` is a test double, allowed only where the e2e backend opts in (research R15)."""
    if provider == "scripted":
        return settings.agent_allow_scripted_provider
    return provider in ("anthropic", "ollama")


class SettingsInvalid(ValueError):
    def __init__(self, field: str, message: str) -> None:
        super().__init__(message)
        self.field = field
        self.message = message


def validate(update) -> None:
    """Rules beyond the schema's ranges (FR-016): raise `SettingsInvalid` naming the field."""
    from urllib.parse import urlparse

    if not provider_allowed(update.agent_provider):
        raise SettingsInvalid("agent_provider", "this provider can't be used here")
    parsed = urlparse(update.agent_base_url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise SettingsInvalid("agent_base_url", "must be an http:// or https:// address")
    if not update.agent_enabled:
        return
    if not update.agent_model:
        raise SettingsInvalid("agent_model", "set a model before switching the agent on")
    if update.agent_provider == "anthropic":
        if not api_key_set():
            raise SettingsInvalid("agent_provider", "no API key is set for the hosted model")
        for field in ("agent_price_per_input_token_usd", "agent_price_per_output_token_usd"):
            if getattr(update, field) is None:
                raise SettingsInvalid(field, "set both token rates before using the hosted model")


async def save(session: AsyncSession, update) -> None:
    validate(update)
    row = await settings_row(session)
    if row is None:
        row = AgentSettings(id=1)
        session.add(row)
    for field, value in update.model_dump().items():
        setattr(row, field, value)
    await session.commit()
