"""POST /architectures/{id}/calculate (spec FR-010, FR-011, FR-012, FR-017, FR-018;
004-canvas-pricing-improvements FR-001) and POST /catalog/calculate-snapshot
(008-ui-updates-corrections, US5, FR-016a, contracts/api.md)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter

from src.api.deps import CurrentUser, DbSession
from src.models.schemas import CalculateSnapshotRequest, CalculationDuration, CalculationResult
from src.services.architecture_service import get_owned_architecture
from src.services.price_calculation import (
    build_transient_architecture,
    calculate_architecture_price,
)

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


@router.post("/catalog/calculate-snapshot", response_model=CalculationResult)
async def calculate_snapshot(
    request: CalculateSnapshotRequest,
    user: CurrentUser,
) -> CalculationResult:
    """Stateless — no `architecture_id`, nothing persisted or ownership-checked beyond the
    existing `CurrentUser` auth dependency (research.md §5). Prices `request.selections` via
    the exact same code path every other calculation uses, so the duration-adjusted
    comparison total for Price Change (FR-016a) is real, never estimated.
    `EmptySnapshotError` (raised by `build_transient_architecture` for an empty list) is
    mapped to a 400 by `src/main.py`'s registered handler.
    """
    architecture = build_transient_architecture(request.selections)
    return calculate_architecture_price(architecture, duration=request.duration)
