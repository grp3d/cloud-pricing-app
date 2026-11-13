"""`/admin/agent/*` and `/admin/users/{id}/agent` — the Admin's agent settings and per-user agent
fields (023-agent-foundation, contracts/agent-api.md "Admin routes", FR-016–FR-019, FR-022a).

Settings take effect from the next message, with no redeploy. The model API key is never
returned; only whether one is set (FR-017).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status

from src.agent import limits, settings_service
from src.api.admin_users import (
    _architecture_count,
    _get_named_user_or_404,
    _to_admin_user_out,
)
from src.api.deps import AdminUser, DbSession
from src.models.schemas import (
    AdminUserAgentUpdate,
    AdminUserOut,
    AgentSettingsOut,
    AgentSettingsUpdate,
)

router = APIRouter(prefix="/admin", tags=["admin"])


async def _settings_out(session) -> AgentSettingsOut:
    effective = await settings_service.effective_settings(session)
    now = datetime.now(UTC)
    return AgentSettingsOut(
        agent_enabled=effective.enabled,
        agent_provider=effective.provider,
        agent_model=effective.model,
        agent_base_url=effective.base_url,
        agent_timeout_seconds=effective.timeout_seconds,
        agent_global_monthly_cap_usd=effective.global_monthly_cap_usd,
        agent_default_user_monthly_inputs=effective.default_user_monthly_inputs,
        agent_price_per_input_token_usd=effective.price_per_input_token_usd,
        agent_price_per_output_token_usd=effective.price_per_output_token_usd,
        api_key_set=settings_service.api_key_set(),
        spend_this_month_usd=await limits.spend_this_month(session, now),
        resets_on=limits.resets_on(now),
    )


@router.get("/agent/settings", response_model=AgentSettingsOut)
async def get_agent_settings(session: DbSession, _admin: AdminUser) -> AgentSettingsOut:
    return await _settings_out(session)


@router.put("/agent/settings", response_model=AgentSettingsOut)
async def put_agent_settings(
    body: AgentSettingsUpdate, session: DbSession, _admin: AdminUser
) -> AgentSettingsOut:
    try:
        await settings_service.save(session, body)
    except settings_service.SettingsInvalid as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=[{"loc": ["body", exc.field], "msg": exc.message, "type": "value_error"}],
        ) from exc
    return await _settings_out(session)


@router.patch("/users/{user_id}/agent", response_model=AdminUserOut)
async def update_user_agent(
    user_id: uuid.UUID, body: AdminUserAgentUpdate, session: DbSession, _admin: AdminUser
) -> AdminUserOut:
    user = await _get_named_user_or_404(user_id, session)
    if body.agent_enabled_for_user is not None:
        user.agent_enabled_for_user = body.agent_enabled_for_user
        if not body.agent_enabled_for_user:
            # Analysis finding I1 (a), FR-020: turning it off ends the preview too.
            user.agent_preview_input_counter = 0
    if body.agent_preview_input_counter is not None:
        user.agent_preview_input_counter = body.agent_preview_input_counter
    if body.clear_monthly_input_limit:
        user.agent_monthly_input_limit = None
    elif body.agent_monthly_input_limit is not None:
        user.agent_monthly_input_limit = body.agent_monthly_input_limit
    await session.commit()
    return await _to_admin_user_out(session, user, await _architecture_count(session, user.id))
