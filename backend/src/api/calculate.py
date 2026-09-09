"""POST /architectures/{id}/calculate (spec FR-010, FR-011, FR-012, FR-017, FR-018;
004-canvas-pricing-improvements FR-001)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter

from src.api.deps import CurrentUser, DbSession
from src.models.schemas import CalculationDuration, CalculationResult
from src.services.architecture_service import get_owned_architecture
from src.services.price_calculation import calculate_architecture_price

router = APIRouter(tags=["calculate"])


@router.post("/architectures/{architecture_id}/calculate", response_model=CalculationResult)
async def calculate_architecture(
    architecture_id: uuid.UUID,
    session: DbSession,
    user: CurrentUser,
    duration: CalculationDuration = CalculationDuration.one_month,
) -> CalculationResult:
    architecture = await get_owned_architecture(architecture_id, session, user)
    return calculate_architecture_price(architecture, duration=duration)
