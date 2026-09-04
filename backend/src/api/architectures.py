"""Architecture endpoints (spec FR-001, FR-002, FR-013, FR-014).

Every route is scoped to `CurrentUser` — no endpoint here ever accepts or returns another
user's Architecture (FR-002).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from src.api.deps import CurrentUser, DbSession
from src.models.orm import Architecture
from src.models.schemas import ArchitectureCreate, ArchitectureDetailOut, ArchitectureSummaryOut
from src.services.architecture_service import get_owned_architecture

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


@router.get("/architectures/{architecture_id}", response_model=ArchitectureDetailOut)
async def get_architecture(
    architecture_id: uuid.UUID, session: DbSession, user: CurrentUser
) -> Architecture:
    return await get_owned_architecture(architecture_id, session, user)


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
