"""`/auth/*` — current-identity resolution and login (012-user-accounts-sharing, spec FR-014-019a).

`POST /auth/login` doubles as "create a password on first use" (research.md §1, contracts/api.md
§3): the server, not the client, decides whether a submitted password sets the account's first
password or verifies an existing one — the client only ever calls this one endpoint either way.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from src.api.deps import CurrentUser, DbSession
from src.models.orm import User
from src.models.schemas import (
    CheckUsernameOut,
    CheckUsernameRequest,
    CurrentUserOut,
    LoginRequest,
)
from src.services.auth_service import hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me", response_model=CurrentUserOut)
async def get_me(user: CurrentUser) -> CurrentUserOut:
    return CurrentUserOut(
        id=user.id, username=user.username, is_admin=user.is_admin, is_active=user.is_active
    )


@router.post("/check-username", response_model=CheckUsernameOut)
async def check_username(body: CheckUsernameRequest, session: DbSession) -> CheckUsernameOut:
    user = (
        await session.execute(select(User).where(User.username == body.username))
    ).scalar_one_or_none()
    if user is None:
        return CheckUsernameOut(exists=False, has_password=False)
    return CheckUsernameOut(exists=True, has_password=user.password_hash is not None)


@router.post("/login", response_model=CurrentUserOut)
async def login(body: LoginRequest, session: DbSession) -> CurrentUserOut:
    user = (
        await session.execute(select(User).where(User.username == body.username))
    ).scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Login failed")

    if user.password_hash is None:
        # First use: this submission *sets* the account's password (FR-017).
        user.password_hash = hash_password(body.password)
        await session.commit()
    elif not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Login failed")

    return CurrentUserOut(
        id=user.id, username=user.username, is_admin=user.is_admin, is_active=user.is_active
    )
