"""Per-user preferences on the server (019, data-model §1, research R12, FR-020 to FR-025).

One typed JSON row per user, named or guest, deleted with the user (FK cascade). A write
replaces whole sections — `migrated_from_browser`, `workspace`, `trends.charts`,
`trends.movers` — and the last write wins per section.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.orm import UserPreferences
from src.models.schemas import Preferences, PreferencesOut, PreferencesPatch

SCHEMA_VERSION = 1


def _out(row: UserPreferences | None) -> PreferencesOut:
    if row is None:
        return PreferencesOut(schema_version=SCHEMA_VERSION, data=Preferences())
    return PreferencesOut(
        schema_version=row.schema_version, data=Preferences.model_validate(row.data or {})
    )


async def get_preferences(session: AsyncSession, user_id: uuid.UUID) -> PreferencesOut:
    """The stored preferences, or the empty defaults when the user has none yet."""
    return _out(await session.get(UserPreferences, user_id))


async def patch_preferences(
    session: AsyncSession, user_id: uuid.UUID, patch: PreferencesPatch
) -> PreferencesOut:
    row = await session.get(UserPreferences, user_id, with_for_update=True)
    current = Preferences.model_validate(row.data if row is not None else {})
    data = current.model_dump(mode="json", exclude_none=True)
    sent = patch.model_fields_set

    if "migrated_from_browser" in sent and patch.migrated_from_browser is not None:
        data["migrated_from_browser"] = patch.migrated_from_browser
    if "workspace" in sent:
        _replace(data, "workspace", patch.workspace)
    if "trends" in sent:
        if patch.trends is None:
            data.pop("trends", None)
        else:
            trends = data.setdefault("trends", {})
            for section in ("charts", "movers"):
                if section in patch.trends.model_fields_set:
                    _replace(trends, section, getattr(patch.trends, section))
            if not trends:
                data.pop("trends")

    validated = Preferences.model_validate(data).model_dump(mode="json", exclude_none=True)
    if row is None:
        row = UserPreferences(user_id=user_id, data=validated, schema_version=SCHEMA_VERSION)
        session.add(row)
    else:
        row.data = validated
        row.updated_at = func.now()
    await session.commit()
    await session.refresh(row)
    return _out(row)


def _replace(target: dict, key: str, value) -> None:
    if value is None:
        target.pop(key, None)
    else:
        target[key] = value.model_dump(mode="json", exclude_none=True)
