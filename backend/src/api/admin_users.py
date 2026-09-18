"""`/admin/users` — administrator-only user management (012-user-accounts-sharing, spec FR-004-013).

Every route here is gated on `AdminUser` (`require_admin`, `src/api/deps.py`). The seeded
default Admin account (`User.is_default_admin`) can never be deactivated or purged (FR-013) —
enforced here in the service/route layer, not the schema, matching this codebase's existing
pattern for cross-row business rules that a single `CHECK` constraint can't express.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from src.api.deps import AdminUser, DbSession
from src.models.orm import Architecture, User
from src.models.schemas import (
    AdminPasswordUpdate,
    AdminUserActiveUpdate,
    AdminUserCreate,
    AdminUserOut,
)
from src.services.auth_service import hash_password

router = APIRouter(prefix="/admin", tags=["admin"])


def _to_admin_user_out(user: User) -> AdminUserOut:
    return AdminUserOut(
        id=user.id,
        username=user.username,
        is_active=user.is_active,
        has_password=user.password_hash is not None,
        password_hash_suffix=user.password_hash[-4:] if user.password_hash else None,
        is_admin=user.is_admin,
        is_default_admin=user.is_default_admin,
    )


async def _get_named_user_or_404(user_id: uuid.UUID, session: DbSession) -> User:
    user = await session.get(User, user_id)
    if user is None or user.username is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


@router.get("/users", response_model=list[AdminUserOut])
async def list_users(session: DbSession, _admin: AdminUser) -> list[AdminUserOut]:
    result = await session.execute(
        select(User).where(User.username.is_not(None)).order_by(User.username)
    )
    return [_to_admin_user_out(u) for u in result.scalars().all()]


@router.post("/users", response_model=AdminUserOut, status_code=201)
async def create_user(
    body: AdminUserCreate, session: DbSession, _admin: AdminUser
) -> AdminUserOut:
    existing = (
        await session.execute(select(User).where(User.username == body.username))
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=400, detail="Username already exists")
    user = User(username=body.username, is_active=True)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return _to_admin_user_out(user)


@router.patch("/users/{user_id}", response_model=AdminUserOut)
async def set_user_active(
    user_id: uuid.UUID, body: AdminUserActiveUpdate, session: DbSession, _admin: AdminUser
) -> AdminUserOut:
    user = await _get_named_user_or_404(user_id, session)
    if user.is_default_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The default Admin account cannot be deactivated",
        )
    user.is_active = body.is_active
    await session.commit()
    await session.refresh(user)
    return _to_admin_user_out(user)


@router.put("/users/{user_id}/password", response_model=AdminUserOut)
async def set_user_password(
    user_id: uuid.UUID, body: AdminPasswordUpdate, session: DbSession, _admin: AdminUser
) -> AdminUserOut:
    user = await _get_named_user_or_404(user_id, session)
    user.password_hash = hash_password(body.password)
    await session.commit()
    await session.refresh(user)
    return _to_admin_user_out(user)


@router.delete("/users/{user_id}", status_code=204)
async def delete_user(user_id: uuid.UUID, session: DbSession, _admin: AdminUser) -> None:
    user = await _get_named_user_or_404(user_id, session)
    if user.is_default_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The default Admin account cannot be purged",
        )
    # Deleted through the ORM (not a bulk `DELETE`), so each Architecture's existing
    # `cascade="all, delete-orphan"` relationships (orm.py) cascade to its Collections,
    # DataConnectors, and SKUSelections — there's no DB-level `ON DELETE CASCADE` on
    # `architecture_id`/`collection_id` for a raw SQL delete to rely on instead.
    owned = (
        await session.execute(select(Architecture).where(Architecture.user_id == user.id))
    ).scalars().all()
    for architecture in owned:
        await session.delete(architecture)
    await session.delete(user)
    await session.commit()
