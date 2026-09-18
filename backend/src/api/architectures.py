"""Architecture endpoints (spec FR-001, FR-002, FR-013, FR-014).

Every route is scoped to `CurrentUser` — no endpoint here ever accepts or returns another
user's Architecture (FR-002).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.api.deps import CurrentUser, DbSession
from src.models.orm import Architecture, Collection, DataConnector, User
from src.models.schemas import (
    ArchitectureCreate,
    ArchitectureDetailOut,
    ArchitectureImportRequest,
    ArchitectureSummaryOut,
    ArchitectureUpdate,
    ImportableArchitectureGroupOut,
    ImportableArchitectureOut,
    ImportableArchitecturesOut,
)
from src.services.architecture_import import import_architecture
from src.services.architecture_service import attach_units_to_architecture, get_owned_architecture

router = APIRouter(tags=["architectures"])


@router.post("/architectures", response_model=ArchitectureSummaryOut, status_code=201)
async def create_architecture(
    body: ArchitectureCreate, session: DbSession, user: CurrentUser
) -> Architecture:
    if body.provider != "aws":
        raise HTTPException(status_code=400, detail="Only 'aws' is supported in v1")
    architecture = Architecture(user_id=user.id, name=body.name, provider=body.provider)
    session.add(architecture)
    await session.commit()
    await session.refresh(architecture)
    return architecture


@router.get("/architectures", response_model=list[ArchitectureSummaryOut])
async def list_architectures(
    session: DbSession, user: CurrentUser, provider: str = "aws"
) -> list[Architecture]:
    result = await session.execute(
        select(Architecture)
        .where(
            Architecture.user_id == user.id,
            Architecture.provider == provider,
            Architecture.deleted_at.is_(None),
        )
        .order_by(Architecture.created_at.desc())
    )
    return list(result.scalars().all())


@router.get("/architectures/importable", response_model=ImportableArchitecturesOut)
async def list_importable_architectures(
    session: DbSession, user: CurrentUser
) -> ImportableArchitecturesOut:
    """Every other user's public architectures, grouped by owner and pre-sorted
    (012-user-accounts-sharing, spec FR-023-026): the Admin group always first, other groups
    alphabetical, architecture names alphabetical within a group; an owner with zero public
    architectures never appears."""
    result = await session.execute(
        select(Architecture, User.username)
        .join(User, Architecture.user_id == User.id)
        .where(
            Architecture.is_public.is_(True),
            Architecture.deleted_at.is_(None),
            Architecture.user_id != user.id,
            User.username.is_not(None),
        )
    )
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


@router.post(
    "/architectures/{architecture_id}/import", response_model=ArchitectureSummaryOut,
    status_code=201,
)
async def import_public_architecture(
    architecture_id: uuid.UUID,
    body: ArchitectureImportRequest,
    session: DbSession,
    user: CurrentUser,
) -> Architecture:
    """Deep-copies a public architecture owned by someone else into the caller's own list
    (spec FR-029) — the copy is fully independent from the moment it's created."""
    if user.username is None:
        # FR-027/Edge Cases: the Import action is never shown to a guest; this is the
        # defensive backend-side twin of that UI rule.
        raise HTTPException(status_code=403, detail="Guests cannot import architectures")
    result = await session.execute(
        select(Architecture)
        .where(
            Architecture.id == architecture_id,
            Architecture.is_public.is_(True),
            Architecture.deleted_at.is_(None),
            Architecture.user_id != user.id,
        )
        .options(
            selectinload(
                Architecture.collections.and_(Collection.deleted_at.is_(None))
            ).selectinload(Collection.sku_selections),
            selectinload(Architecture.connectors).selectinload(DataConnector.sku_selection),
        )
    )
    source = result.scalar_one_or_none()
    if source is None:
        raise HTTPException(status_code=404, detail="Architecture not found")
    return await import_architecture(session, source, user, body.name)


@router.get("/architectures/{architecture_id}", response_model=ArchitectureDetailOut)
async def get_architecture(
    architecture_id: uuid.UUID, session: DbSession, user: CurrentUser
) -> ArchitectureDetailOut:
    architecture = await get_owned_architecture(architecture_id, session, user)
    detail = ArchitectureDetailOut.model_validate(architecture)
    # `unit` lives only in the read-only pricing data (never a stored column), so it can't
    # come from ORM-attribute serialization above — batch-resolve and attach it across the
    # whole tree in one DuckDB query (003-service-selection-improvements, FR-004/FR-005).
    attach_units_to_architecture(detail, architecture)
    return detail


@router.patch("/architectures/{architecture_id}", response_model=ArchitectureSummaryOut)
async def update_architecture(
    architecture_id: uuid.UUID, body: ArchitectureUpdate, session: DbSession, user: CurrentUser
) -> Architecture:
    """Owner-only public/private toggle (012-user-accounts-sharing, spec FR-020-022)."""
    result = await session.execute(
        select(Architecture).where(
            Architecture.id == architecture_id,
            Architecture.user_id == user.id,
            Architecture.deleted_at.is_(None),
        )
    )
    architecture = result.scalar_one_or_none()
    if architecture is None:
        raise HTTPException(status_code=404, detail="Architecture not found")
    if body.is_public and user.username is None:
        raise HTTPException(
            status_code=403, detail="A guest-owned architecture can never be made public"
        )
    architecture.is_public = body.is_public
    await session.commit()
    await session.refresh(architecture)
    return architecture


@router.delete("/architectures/{architecture_id}", status_code=204)
async def delete_architecture(
    architecture_id: uuid.UUID, session: DbSession, user: CurrentUser
) -> None:
    """Soft delete (FR-014). Idempotent: deleting an already-deleted Architecture is a no-op 204."""
    result = await session.execute(
        select(Architecture).where(
            Architecture.id == architecture_id, Architecture.user_id == user.id
        )
    )
    architecture = result.scalar_one_or_none()
    if architecture is None:
        return
    if architecture.deleted_at is None:
        architecture.deleted_at = datetime.now(UTC)
        await session.commit()
