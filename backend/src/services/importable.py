"""The architectures a user can import (012-user-accounts-sharing, spec FR-023–FR-026).

Every other named user's public, non-deleted architectures, grouped by owner: the Admin's group
always first, other groups alphabetical, names alphabetical within a group; an owner with no
public architectures never appears. With `provider`, only that provider's (021, research R12).
Shared by `GET /architectures/importable` and the agent's operation (023, US2), so both list
exactly the same thing.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.orm import Architecture, User
from src.models.schemas import (
    ImportableArchitectureGroupOut,
    ImportableArchitectureOut,
    ImportableArchitecturesOut,
)


async def importable_architectures(
    session: AsyncSession, user: User, provider: str | None = None
) -> ImportableArchitecturesOut:
    query = (
        select(Architecture, User.username)
        .join(User, Architecture.user_id == User.id)
        .where(
            Architecture.is_public.is_(True),
            Architecture.deleted_at.is_(None),
            Architecture.user_id != user.id,
            User.username.is_not(None),
        )
    )
    if provider is not None:
        query = query.where(Architecture.provider == provider)
    result = await session.execute(query)
    by_owner: dict[str, list[Architecture]] = {}
    for architecture, owner_username in result.all():
        by_owner.setdefault(owner_username, []).append(architecture)

    other_owners = sorted((o for o in by_owner if o != "Admin"), key=str.lower)
    ordered_owners = (["Admin"] if "Admin" in by_owner else []) + other_owners

    return ImportableArchitecturesOut(
        groups=[
            ImportableArchitectureGroupOut(
                owner_username=owner,
                architectures=[
                    ImportableArchitectureOut(id=a.id, name=a.name)
                    for a in sorted(by_owner[owner], key=lambda a: a.name)
                ],
            )
            for owner in ordered_owners
        ]
    )
