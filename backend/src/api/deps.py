"""Shared FastAPI dependencies: DB session and the current-user identity (spec FR-002).

v1 needs a real, distinct, stable user identity (per the spec's Clarifications) but not a full
login UX — per research.md this is a planning-level implementation detail. Here it's a
lightweight bearer-token header: the token *is* the user id. This keeps every Architecture
genuinely scoped to a real user (no anonymous/global sharing) while deferring an actual
login/session system to a later feature, exactly as the spec's Assumptions describe.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.session import get_session
from src.models.orm import User

DbSession = Annotated[AsyncSession, Depends(get_session)]


async def get_current_user(
    session: DbSession,
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    """Resolve (and lazily create) the User identified by the bearer token.

    `Authorization: Bearer <user-id>` — a stable client-generated UUID is expected. Missing or
    malformed headers are rejected; this never falls back to a shared/global user (FR-002).
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization header",
        )
    token = authorization.removeprefix("Bearer ").strip()
    try:
        user_id = uuid.UUID(token)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid bearer token"
        ) from exc

    user = await session.get(User, user_id)
    if user is None:
        user = User(id=user_id)
        session.add(user)
        await session.commit()
    elif user.username is not None and not user.is_active:
        # A named (non-guest) account the admin has deactivated (012-user-accounts-sharing,
        # spec FR-008) — enforced on the *next* auth check, not instantly (spec Edge Cases).
        # Guest rows have no `is_active` concept of their own beyond the always-true default.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Account is deactivated"
        )
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def require_admin(user: CurrentUser) -> User:
    """Gate admin-only routes (012-user-accounts-sharing, spec FR-003) on `User.is_admin`."""
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user


AdminUser = Annotated[User, Depends(require_admin)]
