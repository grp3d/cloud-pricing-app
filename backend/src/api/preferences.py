"""GET and PATCH /me/preferences (019, contracts §7). The caller's own preferences only,
through the existing identity: a named user or a guest."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from src.api.deps import CurrentUser, DbSession
from src.models.schemas import PreferencesOut, PreferencesPatch
from src.services.preferences_service import get_preferences, patch_preferences

router = APIRouter(tags=["preferences"])


@router.get("/me/preferences", response_model=PreferencesOut, response_model_exclude_none=True)
async def read_preferences(session: DbSession, user: CurrentUser) -> PreferencesOut:
    return await get_preferences(session, user.id)


@router.patch("/me/preferences", response_model=PreferencesOut, response_model_exclude_none=True)
async def update_preferences(
    body: PreferencesPatch, session: DbSession, user: CurrentUser
) -> PreferencesOut:
    if "appearance" in body.model_fields_set and user.username is None:
        # 027 (FR-005): a guest's theme isn't saved. Nothing in this patch is saved either.
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="theme_not_saved_for_guests")
    return await patch_preferences(session, user.id, body)
